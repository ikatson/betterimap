# coding: utf-8

"""Utils for logging into imap services and parsing emails."""

import datetime
import email
import email.message
import email.utils
import email.header
import imaplib
import logging
import json
import re
import socket
import time
import threading
import Queue
import urllib
import urllib2

try:
    import chardet
except ImportError:
    chardet = None

from . import imapUTF7

log = logging.getLogger(__name__)

# Default maximum amount of messages to fetch.
FETCH_LIMIT = 100

ZERO = datetime.timedelta(0)

ATTACH_FILENAME_RE = re.compile(r'name=(\S+)')
ATTACH_FILENAME_RE_QUOTED = re.compile(r'name="([^"]*?)"')


class Error(Exception):
    pass


class NotSupported(Error):
    pass


class ProgrammingError(Error):
    pass


class ManualStop(Error):
    pass


class AuthError(Error):
    pass


class OAuth2Error(AuthError):
    pass


class UTC(datetime.tzinfo):
    """UTC timezone, copied from stdlib documentation."""

    def utcoffset(self, _):
        return ZERO

    def tzname(self, _):
        return "UTC"

    def dst(self, _):
        return ZERO


class Attachment(object):
    """An email message attachment."""

    def __init__(self, msg):
        assert isinstance(msg, MessageWrapper)
        self.msg = msg

    def __str__(self):
        return self.filename

    def __unicode__(self):
        return self.filename

    def __len__(self):
        return len(self.data or '')

    def __repr__(self):
        if self.filename:
            filename = self.filename.encode('utf-8')
        else:
            filename = None
        return '<Attachment %s, %s, size %s>' % (
            filename, self.content_type, len(self))

    @property
    def filename(self):
        """String attachment filename, if it's defined."""
        return self.msg.attachment_filename

    @property
    def data(self):
        """String payload of the attachment."""
        return self.msg.get_payload(decode=True)

    @property
    def size(self):
        """Integer length of the attachment."""
        return len(self)

    @property
    def content_type(self):
        """String content type of the attachment."""
        return self.msg.get_content_type()


class MessageWrapper(object):
    """A wrapper for email.message.Message with some convenient methods."""

    # How to map certain bad-formatted encodings to python encodings.
    BAD_ENCODING_MAP = {'cp-1251': 'cp1251'}

    # These encodings will be tried as a last resort, if the message does not
    # decode with the provided encoding, or it is empty.
    LAST_RESORT_ENCODINGS = ('windows-1251', 'koi8-r', 'utf-8')

    # If chardet is used in decoding headers, this confidence will be required
    # for the header to decode successfully.
    CHARDET_CONFIDENCE = 0.7

    def __init__(self, email_message):
        assert isinstance(email_message, email.message.Message)
        self.msg = email_message
        # These ones may be set by the IMAPAdapter.
        self.uid = None
        self.x_gm_msgid = None

    def __getattr__(self, attr):
        return getattr(self.msg, attr)

    def __getitem__(self, item):
        return self.msg[item]

    @property
    def from_addr(self):
        """A tuple (name, addr) parsed from From: header."""
        return email.utils.parseaddr(self.get_header('From'))

    @property
    def subject(self):
        """Unicode email subject."""
        return self.get_header('subject')

    @property
    def to(self):
        """A list of 2-tuples (name, addr) parsed from To: header."""
        return self._parse_addrlist('To')

    @property
    def cc(self):
        """A list of 2-tuples (name, addr) parsed from Cc: header."""
        return self._parse_addrlist('Cc')

    @property
    def received(self):
        """Timezone-aware date from the "Received:" header."""
        received = self.get_header('received').split('\n')[-1].strip()
        received = received.split(';')[-1]
        return self.parse_date(received)

    @property
    def date(self):
        """Timezone-aware date from the "Date:" header."""
        date = self.get_header('date')
        try:
            return self.parse_date(date)
        except TypeError:
            log.exception('Error parsing date header %s', date)

    def attachments(self):
        """Get a list of betterimap.Attachment email attachments."""
        return map(Attachment, self._attachments())

    def plaintext(self):
        """Extract the plaintext version of this email."""
        msg = self._get_msg_by_content_type('text/plain')
        if msg:
            return msg.get_text()

    def html(self):
        """Extract the html version of this email."""
        msg = self._get_msg_by_content_type('text/html')
        if msg:
            return msg.get_text()

    def get_text(self, check_subtype=None):
        """Extract unicode text from payload.

        If check_subtype is provided, the text is extracted only if
        the message subtype matches, e.g. "plain" or "html"
        """
        if self.get_content_maintype() != 'text':
            return
        if check_subtype and self.get_content_subtype != check_subtype:
            return
        payload = self.get_payload(decode=True)
        if not payload:
            return
        charset = self.get_content_charset()
        if charset:
            try:
                return payload.decode(charset)
            except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
                pass
        if chardet:
            # try to guess the charset if chardet is available
            detected = chardet.detect(payload)
            if detected['confidence'] > self.CHARDET_CONFIDENCE:
                payload = payload.decode(detected['encoding'])
        return payload

    def get_payload(self, *args, **kwargs):
        """Wrap all payload messages into MessageWrapper."""
        payload = self.msg.get_payload(*args, **kwargs)
        if not isinstance(payload, list):
            return payload
        result = []
        for i in payload:
            if isinstance(i, email.message.Message):
                i = MessageWrapper(i)
            result.append(i)
        return result

    def walk(self):
        """Recursively walk this email, yields MessageWrapper objects."""
        for msg in self.msg.walk():
            yield MessageWrapper(msg)

    @property
    def attachment_filename(self):
        """Parse attachment filename from Content-Disposition header."""
        content_disposition = self.get_header('content-disposition')
        if not content_disposition or 'attachment' not in content_disposition:
            return
        match = ATTACH_FILENAME_RE_QUOTED.search(content_disposition)
        if not match:
            match = ATTACH_FILENAME_RE.search(content_disposition)
        if not match:
            content_type = self.get_header('content-type')
            match = ATTACH_FILENAME_RE_QUOTED.search(content_type)
            if not match:
                match = ATTACH_FILENAME_RE.search(content_type)
            if not match:
                return
        filename = match.group(1)
        filename, enc = email.header.decode_header(filename)[0]
        if enc:
            filename = filename.decode(enc)
        return filename

    def get_header(self, name, join=True):
        """Get a unicode version of a header by it's name.

        If join=True, returns a unicode object, otherwise a list of unicode
        values.
        """
        hvalue = self.msg[name]
        if not hvalue:
            return
        result = self._get_header(hvalue)
        if join:
            return ' '.join(result)

    @classmethod
    def _get_header(cls, hvalue):
        """Decode an email header value

        Returns a list of unicode objects.
        """
        result = []
        if not hvalue:
            return
        hvalue = cls._fix_header(hvalue)
        seen_encodings = set()

        for hvalue, encoding in email.header.decode_header(hvalue):
            if encoding:
                encoding = cls.BAD_ENCODING_MAP.get(encoding, encoding)
                try:
                    hvalue = hvalue.decode(encoding)
                    seen_encodings.add(encoding)
                except (UnicodeDecodeError, UnicodeEncodeError, LookupError):
                    pass
            result.append(hvalue)

        # Now try to decode the headers which where not decoded automatically.
        for idx, hvalue in enumerate(result):
            if isinstance(hvalue, unicode):
                continue
            # Try to decode the undecoded header with one of the seen encodings.
            for encoding in seen_encodings:
                try:
                    hvalue = hvalue.decode(encoding)
                except UnicodeDecodeError:
                    continue
                break
            if isinstance(hvalue, unicode):
                result[idx] = hvalue
                continue
            # Try to decode the header with ascii.
            try:
                hvalue = hvalue.decode('ascii')
            except UnicodeDecodeError:
                pass
            else:
                result[idx] = hvalue
                continue
            # Try to guess the charset if chardet is available
            if chardet:
                detected = chardet.detect(hvalue)
                if detected['confidence'] > 0.7:
                    result[idx] = hvalue.decode(detected['encoding'])
                    continue
            # Try some common encodings (this lib was written for russian
            # emails).
            for encoding in cls.LAST_RESORT_ENCODINGS:
                try:
                    hvalue = result[idx] = hvalue.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            # Give up.
            if not isinstance(hvalue, unicode):
                if seen_encodings:
                    encoding = list(seen_encodings)[0]
                else:
                    encoding = 'utf-8'
                result[idx] = hvalue.decode(encoding, errors='ignore')
        return result

    @staticmethod
    def _fix_header(header):
        """Try to fix an invalid header."""
        # Add space between address and header so it parses with decode_header.
        missing_space_re = re.compile(r'(=\?.*?\?=)(<.*?@.*?>)')
        header = missing_space_re.sub(r'\1 \2', header)
        return header

    @staticmethod
    def parse_date(string_date, default_tz=UTC()):
        """Parse a date string and return an aware datetime.datetime object.

        default_tz: what timezone to use, if no timezone is provided. If None,
          will return a naive datetime in this case.
        """
        tup = email.utils.parsedate_tz(string_date)
        if not tup:
            return
        # Timezone present.
        if tup[9]:
            date = datetime.datetime.fromtimestamp(
                time.mktime(tup[:9]) - tup[9])
            date = date.replace(tzinfo=UTC())
        else:
            date = datetime.datetime.fromtimestamp(time.mktime(tup[:9]))
            if default_tz:
                date = date.replace(tzinfo=default_tz)
        return date

    # These methods are here just to appear in shell completion.
    def get_content_maintype(self):
        return self.msg.get_content_maintype()

    def get_content_subtype(self):
        return self.msg.get_content_subtype()

    def get_content_charset(self):
        return self.msg.get_content_charset()

    def get_content_type(self):
        return self.msg.get_content_type()

    def content_transfer_encoding(self):
        return self.get_header('content-transfer-encoding')

    def _get_msg_by_content_type(self, content_type):
        """Recursively search for a message with needed content type."""
        for msg in self.walk():
            if msg.get_content_type() == content_type:
                return msg

    def _attachments(self):
        """Get attachments to this email as email.Messages."""
        result = []
        if self.get_content_type() == 'multipart/mixed':
            payload = self.get_payload()
            for i in payload:
                if i.get_content_maintype() not in ('multipart',):
                    result.append(i)
        return result

    def _parse_addrlist(self, header_name):
        addrs = self.get_header(header_name)
        if not addrs:
            return
        addrs = addrs.split(',')
        addrs = [i for i in addrs if i]
        return map(email.utils.parseaddr, addrs)

    def __str__(self):
        return str(self.msg)

    def __unicode__(self):
        return unicode(self.msg)

    def __repr__(self):
        return '<MesageWrapper: %r>' % self.msg


# Fetch specifications.
FETCH_RFC822 = '(RFC822)'

# Use this if you don't need the email content.
FETCH_HEADERS_ONLY = '(BODY[HEADER.FIELDS (SUBJECT FROM DATE TO CC)])'


def _idle_imap4_connection(connection):
    """Wait for messages on imaplib.IMAP4, yield tuples (uid, string)."""
    assert isinstance(connection, imaplib.IMAP4)
    tag = connection._new_tag()
    connection.send("%s IDLE\r\n" % tag)
    response = connection.readline()
    if response != '+ idling\r\n':
        raise Error("IDLE not handled? : %s" % response)
    while True:
        resp = connection.readline()
        uid, message = resp[2:-2].split(' ')
        yield uid, message


def _send_done_imap4_connection(connection):
    connection.send("DONE\r\n")


class IMAPFolder(object):
    """An abstraction over an IMAP folder.

    Decodes folder names from UTF7, and splits into tags and names.
    """

    folder_re = re.compile(r'^\((.*)\) ".*" "?(.*)"?$')

    def __init__(self, folder_string):
        self.name = None
        self.flags = set()
        self.orig_string = folder_string
        if not isinstance(self.orig_string, unicode):
            self.orig_string = imapUTF7.imapUTF7Decode(self.orig_string)
        self._parse()

    def _parse(self):
        match = self.folder_re.match(self.orig_string)
        assert match, 'Cannot parse %s' % self.orig_string
        flags, self.name = match.groups()
        for flag in flags.split(' '):
            flag = flag.strip('\\')
            if flag:
                self.flags.add(flag)
        self.name = self.name.strip('"')

    def __unicode__(self):
        return self.name

    def __str__(self):
        return self.name

    def __repr__(self):
        return '<IMAPFolder: %s>' % self.name.encode('utf-8')


class IMAPAdapter(object):
    """A wrapper around IMAP4, that decorates it with useful functionality."""

    host = None
    port = None
    ssl = None

    # Heuristically determined folder names, sorry for only English and Russian
    # support here.
    inbox_folder_re = re.compile(u'Inbox|Входящие', re.UNICODE | re.IGNORECASE)
    inbox_folder_strict_re = re.compile(
        u'.*(Inbox|Входящие)$', re.UNICODE | re.IGNORECASE)
    sent_folder_re = re.compile(
        u'Sent|Отправленные', re.UNICODE | re.IGNORECASE)
    trash_folder_re = re.compile(
        u'Trash|Корзина', re.UNICODE | re.IGNORECASE
    )

    imap_cls = imaplib.IMAP4
    imap_cls_ssl = imaplib.IMAP4_SSL

    def __init__(
        self, login=None, password=None, host=None, port=None, ssl=None
    ):
        """Connect and authenticate with an IMAP4 server.

        Args:
            login: a string login, optional
            password: a string password, optional
            host: the servername, optional if provided in the subclass
            port: the integer port, optional
            ssl: if True, will use SSL connection.
        """
        self.host = host or self.host
        self.port = port or self.port
        self.ssl = ssl or self.ssl
        assert self.host, 'Server should not be empty'
        self.login = login
        self.password = password
        if self.ssl:
            self.imap_cls = self.imap_cls_ssl
        self._connect_and_login()

    def _authenticate(self, login, password):
        assert login and password, 'Login and/or password missing'
        self.mail.login(login, password)

    def _connect_and_login(self, login=None, password=None):
        login = login or self.login
        password = password or self.password
        if self.port:
            self.mail = self.imap_cls(self.host, self.port)
        else:
            self.mail = self.imap_cls(self.host)
        self._authenticate(login, password)
        self.selected_folder = None
        self.total = None
        self._folder_list = None
        self.idling = False

    def reconnect(self):
        """Reconnect and reselect the currently selected folder."""
        folder = self.selected_folder
        self._connect_and_login()
        if folder:
            self.select(folder)

    def _copy_args(self):
        # This is moved into a separate method because Gmail overrides it.
        return [self.login, self.password], dict(
            host=self.host, port=self.port, ssl=self.ssl)

    def copy(self):
        """Create a new IMAP4Adapter like self, and connect to it."""
        folder = self.selected_folder
        args, kwargs = self._copy_args()
        new_conn = self.__class__(*args, **kwargs)
        if folder:
            new_conn.select(folder)
        return new_conn

    def _idle(self, fetch_spec, msg_q):
        self.idling = True
        while self.idling:
            try:
                uid = None
                for uid, message in _idle_imap4_connection(self.mail):
                    if not self.idling:
                        uid = None
                        break
                    if message != 'EXISTS':
                        continue
                    _send_done_imap4_connection(self.mail)
                    break
                if not uid:
                    continue
                # ManualStop requested.
                if not self.idling:
                    break

                message = self.fetch_email_by_uid(uid, fetch_spec=fetch_spec)
                msg_q.put(message)
            except NotSupported, e:
                msg_q.put(e)
                break
            except socket.error:
                self.reconnect()
                self.idling = True

    def idle(self, fetch_spec=FETCH_HEADERS_ONLY, copy=True):
        """Starts IDLE in a separate thread.

        Args:
          fetch_spec: in what RFC to fetch the email values. You can set
            to FETCH_RFC822 to yield whole email objects.
          copy: if True, which is the default, do not touch the existing
            connection, but create a new one.

        Returns a tuple:
          - first is a function, which you should call with no arguments, if you
            want to stop idling.
          - an iterable of MessageWrapper objects that you can consume.
        """
        if not self.selected_folder:
            raise ProgrammingError('You should select a folder before idling')
        if copy:
            conn = self.copy()
        else:
            conn = self
        q = Queue.Queue()
        t = threading.Thread(target=conn._idle, args=(fetch_spec, q))
        t.daemon = True
        t.start()

        def stop():
            conn.idling = False
            q.put(ManualStop())

        def iter_messages():
            while True:
                result = q.get()
                if isinstance(result, MessageWrapper):
                    yield result
                    continue
                elif isinstance(result, ManualStop):
                    raise StopIteration
                elif isinstance(result, Exception):
                    raise result
        return stop, iter_messages()

    def search_folders(self, name_re=None, flags=None):
        """Yield folders matching the arguments.

        Args:
          name_re: a string or regexp to for the folder name, e.g. "Sent".
          flags: an iterable of string folder flags, e.g. ["Trash"]
        Yields:
          IMAP4Folder objects
        """
        assert name_re or flags
        for folder in self.list():
            if flags and set(flags).issubset(folder.flags):
                yield folder
            elif name_re:
                if isinstance(name_re, basestring):
                    if re.search(
                        name_re, folder.name, re.UNICODE | re.IGNORECASE
                    ):
                        yield folder
                elif name_re.search(folder.name):
                    yield folder

    def get_sent_folder(self):
        """Try to get the "Sent" folder. Return an IMAPFolder."""
        try:
            return self.get_sent_folders()[0]
        except IndexError:
            return

    def get_sent_folders(self):
        """Try to get all "Sent" folders. Returns a list of IMAPFolders."""
        return list(self.search_folders(
            name_re=self.sent_folder_re, flags=('Sent',)))

    def get_trash_folder(self):
        """Try to get the "Trash" folders. Returns a list of IMAPFolders."""
        try:
            return self.get_trash_folders()[0]
        except IndexError:
            return

    def get_trash_folders(self):
        """Try to get all "Trash" folders. Returns a list of IMAPFolders."""
        return list(self.search_folders(
            name_re=self.trash_folder_re, flags=('Trash',)))

    def get_inbox_folder(self):
        """Get the inbox folder.

        This folder should always exist, so if it's not found, just 'inbox'
        is returned, so that you can pass the result to .select().

        Returns an IMAPFolder or a string.
        """
        folders = list(self.search_folders(name_re=self.inbox_folder_re))
        if len(folders) == 1:
            return folders[0]
        elif not folders:
            return 'inbox'
        # Ok, now there's ambiguity, we have several folders named "inbox".
        for folder in folders:
            if self.inbox_folder_strict_re.match(folder.name):
                return folder
        # Give up.
        return 'inbox'

    def select(self, folder, *args, **kwargs):
        """Select a folder by name. Also accepts IMAPFolder objects."""
        if isinstance(folder, IMAPFolder):
            folder = folder.name
        if self.selected_folder == folder:
            return self.total
        status, data = self.mail.select(self._encode(folder), *args, **kwargs)
        assert status == 'OK', data[0]
        self.selected_folder = folder
        self.total = int(data[0])
        return self.total

    def _encode(self, string):
        """Encode a string to UTF7 if it's unicode."""
        if isinstance(string, unicode):
            return imapUTF7.imapUTF7Encode(string)
        return string

    def _decode(self, string):
        """Decode a string from UTF7 if it's not unicode."""
        if isinstance(string, unicode):
            return string
        return imapUTF7.imapUTF7Decode(string)

    def search(self, query='ALL', reverse=True, **kwargs):
        """Fetch and parse "limit" emails by search query.

        Args:
            query: an IMAP4 query to search the emails for.
            reverse: if True (default), the newest email is the first to come.

        Yields MessageWrapper objects.

        For a more high-level method see search_emails().
        """
        if isinstance(query, unicode):
            query = query.encode('utf-8')
        status, data = self.mail.search('utf-8', query)
        assert status == 'OK', data[0]
        if data[0]:
            uids = data[0].split()
        else:
            uids = []
        log.info(
            'IMAP search in "%s", %s found, query "%s", kwargs %s',
            self.selected_folder, len(uids), query, kwargs)
        if reverse:
            uids.reverse()
        return self._fetch_emails_by_uids(uids, **kwargs)

    def list(self):
        """Return a list of IMAPFolder objects for this connection."""
        if self._folder_list:
            return self._folder_list
        status, data = self.mail.list()
        if status != 'OK':
            raise Error(data[0])
        folder_list = map(self._decode, data)
        self._folder_list = map(IMAPFolder, folder_list)
        return self._folder_list

    def fetch_email_by_uid(self, uid, fetch_spec=FETCH_RFC822):
        """Fetch an EmailMessage by uid.

        Args:
            uid: the uid of the email, only makes sense during this connection.
            fetch_spec: RFC822 fetch specification.

        Returns:
            MessageWrapper

        Raises:
            AssertionError, if the server does not return OK.

        If you want to fetch only certain headers, set fetch_spec to
        e.g. '(BODY[HEADER.FIELDS (SUBJECT FROM DATE TO CC)])', this is
        already defined in FETCH_HEADERS_ONLY in this module.
        """
        status, data = self.mail.fetch(uid, fetch_spec)
        if status != 'OK':
            raise Error(data[0])
        return self.parse_email(data[0][1])

    def _fetch_emails_by_uids(self, uids, limit=FETCH_LIMIT, **kwargs):
        """Fetch and parse emails by uids."""
        limit = limit or -1
        for uid in uids:
            msg = self.fetch_email_by_uid(uid, **kwargs)
            msg.uid = uid
            yield msg
            limit -= 1
            if limit == 0:
                break

    def parse_email(self, email_string):
        """Convert an email string to MessageWrapper."""
        msg = email.message_from_string(email_string)
        return MessageWrapper(msg)

    def easy_search(
        self, since=None, before=None, subject=None, sender=None,
        exact_date=None, headers=None, fetch_spec=FETCH_RFC822,
        other_queries=(),
        **kwargs
    ):
        """An intelligent generic search function.

        Args (all optional):
            since: the date since which to search emails for.
            before: the date before which to search emails for.
            subject: the subject to search for.
            sender: the sender to search for.
            exact_date: the exact_date to search for.
            headers: a dictionary of headers to search for.
            fetch_spec: in what form to yield emails
            other_queries: additonal string IMAP queries.
        """
        if since and before:
            assert before > since
        if exact_date and (since or before):
            raise ProgrammingError(
                'If exact_date is specified, since and before should be not')
        if exact_date:
            # We cannot determine date for sure cause of unknown server tz.
            since = exact_date.date() - datetime.timedelta(1)
            before = exact_date.date() + datetime.timedelta(1)
        query = []
        headers = headers or {}
        headers = dict((k.upper(), v) for k, v in headers.iteritems())
        if since:
            query.extend(['SINCE', since.strftime('%d-%b-%Y')])
        if before:
            query.extend(['BEFORE', before.strftime('%d-%b-%Y')])
        assert isinstance(other_queries, (list, tuple))
        query.extend(other_queries)
        if subject:
            try:
                subject = unicode(subject)
            except UnicodeEncodeError:
                raise NotSupported(
                    'Non-unicode subject queries are not supported')
            try:
                headers['SUBJECT'] = subject.encode('ascii')
            except UnicodeEncodeError:
                if not sender:
                    raise NotSupported('Unicode subject search requires sender')
        if sender:
            headers['FROM'] = sender
        for header, value in headers.iteritems():
            value = value.replace('"', r'\"')
            query.extend(['HEADER %s' % header, '"%s"' % value])

        for msg in self.search(query='(%s)' % ' '.join(query),
                               fetch_spec=FETCH_HEADERS_ONLY, **kwargs):
            if subject and subject not in (msg.subject or ''):
                continue
            if exact_date and msg.date != exact_date:
                continue
            if isinstance(since, datetime.datetime) and msg.date < since:
                continue
            if isinstance(before, datetime.datetime) and msg.date > before:
                continue
            if fetch_spec == FETCH_HEADERS_ONLY:
                yield msg
            else:
                yield self.fetch_email_by_uid(msg.uid, fetch_spec=fetch_spec)


class Gmail(IMAPAdapter):
    host = 'imap.gmail.com'
    ssl = True

    @staticmethod
    def get_access_token(refresh_token, client_id, client_secret):
        data = {
            'refresh_token': refresh_token, 'client_id': client_id,
            'client_secret': client_secret, 'grant_type': 'refresh_token'}
        response = urllib2.urlopen(
            'https://accounts.google.com/o/oauth2/token',
            urllib.urlencode(data))
        data = response.read()
        if response.getcode() != 200:
            raise OAuth2Error(
                'Something wrong with oauth2 refresh token request.'
                'Google response: %s', response)
        try:
            data = json.loads(data)
        except ValueError:
            raise OAuth2Error('No JSON found in response:\n%s', data)
        return data

    def __init__(self, *args, **kwargs):
        self.access_token = kwargs.pop('access_token', None)
        self.refresh_token = kwargs.pop('refresh_token', None)
        self.client_id = kwargs.pop('client_id', None)
        self.client_secret = kwargs.pop('client_secret', None)
        self.refresh_token_callback = kwargs.pop('refresh_token_callback', None)
        if self.refresh_token:
            assert self.client_id and self.client_secret, (
                'Using OAuth2 refresh_token requires client_id'
                ' and client_secret')
        super(Gmail, self).__init__(*args, **kwargs)

    def _authenticate(self, login, password=None):
        if (self.access_token or self.refresh_token) and password:
            raise ProgrammingError(
                'Password should be empty if using access tokens')
        if not self.login:
            raise ProgrammingError('Login missing')
        if not (self.access_token or self.refresh_token):
            return self._auth_login(login, password)
        else:
            return self._auth_token(login)

    def _auth_login(self, login, password):
        assert login and password, 'Login and password must be provided'
        self.mail.login(login, password)

    def _auth_token(self, login):
        access_token = self.access_token
        refresh_token = self.refresh_token

        while access_token or refresh_token:
            if not access_token:
                data = self.get_access_token(
                    self.refresh_token, self.client_id, self.client_secret)
                access_token = data['access_token']
                if self.refresh_token_callback:
                    self.refresh_token_callback(data)
                refresh_token = None
            auth_string = self._generate_oauth_string(
                login, access_token)
            try:
                self.mail.authenticate('XOAUTH2', lambda x: auth_string)
                self.access_token = access_token
                break
            except:
                access_token = None
        else:
            raise OAuth2Error('Cannot login to gmail %s with XOAUTH2' % login)

    def get_x_gm_msgid(self, uid):
        """Get the Gmail unique id for the message."""
        # Example response:
        # ('OK', ['1663 (X-GM-MSGID 1417225945689728157)'])
        status, data = self.mail.fetch(uid, '(X-GM-MSGID)')
        assert status == 'OK', data[0]
        result = data[0]
        match = re.match(r'%s \(X-GM-MSGID (.+?)\)' % uid, result)
        if match:
            return match.group(1)

    def _copy_args(self):
        args, kwargs = super(Gmail, self)._copy_args()
        kwargs['access_token'] = self.access_token
        kwargs['refresh_token'] = self.refresh_token
        kwargs['client_id'] = self.client_id
        kwargs['client_secret'] = self.client_secret
        kwargs['refresh_token_callback'] = self.refresh_token_callback
        return args, kwargs

    def easy_search(self, x_gm_msgid=None, **kwargs):
        if x_gm_msgid:
            kwargs.setdefault('other_queries', []).extend([
                'X-GM-MSGID', x_gm_msgid
            ])
        return super(Gmail, self).easy_search(**kwargs)

    def fetch_msg_by_x_gm_msgid(self, x_gm_msgid, fetch_spec=FETCH_RFC822):
        for msg in self.search(
            query='(X-GM-MSGID %s)' % x_gm_msgid, fetch_spec=fetch_spec
        ):
            return msg

    def search(self, *args, **kwargs):
        """Search for message, but also fetch X-GM-MSGID."""
        for msg in super(Gmail, self).search(*args, **kwargs):
            msg.x_gm_msgid = self.get_x_gm_msgid(msg.uid)
            yield msg

    def _generate_oauth_string(self, user, access_token):
        """Generates an IMAP OAuth2 authentication string.

        See https://developers.google.com/google-apps/gmail/oauth2_overview

        Args:
          username: the username (email address) of the account to authenticate
          access_token: An OAuth2 access token.

        Returns:
          The SASL argument for the OAuth2 mechanism.
        """
        return 'user=%s\1auth=Bearer %s\1\1' % (user, access_token)


class YandexMail(IMAPAdapter):
    host = 'imap.yandex.ru'
    ssl = True


class MailRuMail(IMAPAdapter):
    host = 'imap.mail.ru'
    ssl = True
