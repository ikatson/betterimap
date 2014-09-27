# coding: utf-8

import imaplib
import urllib
import json
import logging

log = logging.getLogger(__name__)

from shared import mail

import datetime

import re
import unittest


INBOX = 0
SENT = 1


class IMAP4Stub(object):
    def __init__(self, *args, **kwargs):
        return

    def login(self, *args, **kwargs):
        return


class IMAPAdapterStub(mail.IMAPAdapter):
    imap_cls = IMAP4Stub
    imap_cls_ssl = IMAP4Stub

    def __init__(self, *args, **kwargs):
        super(IMAPAdapterStub, self).__init__('user', 'password', host='host')


class IMAPFolderTest(unittest.TestCase):
    def test_parse_flags(self):
        fld = mail.IMAPFolder(
            ur'(\\HasNoChildren \\Sent \\Sent) "." "Sent Folder"')
        self.assertEqual(fld.name, u'Sent Folder')
        self.assertSetEqual(fld.flags, set(['HasNoChildren', 'Sent']))

    def test_parse_no_flags(self):
        fld = mail.IMAPFolder(
            u'() "." "Sent Folder"')
        self.assertSetEqual(fld.flags, set())

    def test_parse_utf7(self):
        fld = mail.IMAPFolder(
            r'(\\Unmarked \\HasNoChildren \\Sent) "|" '
            '"&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-"'
        )
        self.assertEqual(fld.name, u'Отправленные')
        self.assertSetEqual(
            fld.flags, set(['Unmarked', 'HasNoChildren', 'Sent']))


class IMAPAdapterTest(unittest.TestCase):

    class IMAPAdapterAmbiguousInboxStub(IMAPAdapterStub):
        def list(self):
            return [
                mail.IMAPFolder(u'() "." "INBOX.Spam"'),
                mail.IMAPFolder(u'() "." "INBOX"'),
            ]

    class IMAPAdapterNoInboxStub(IMAPAdapterStub):
        def list(self):
            return [
                mail.IMAPFolder(u'() "." "SomeFolder"'),
                mail.IMAPFolder(u'() "." "SomeOtherFolder"'),
            ]

    def test_get_inbox_folder_ambiguous(self):
        imap = self.IMAPAdapterAmbiguousInboxStub(
            'user', 'password')
        inbox = imap.get_inbox_folder()
        self.assertEqual(inbox.name, 'INBOX')

    def test_get_inbox_folder_missing(self):
        imap = self.IMAPAdapterNoInboxStub('user', 'password')
        inbox = imap.get_inbox_folder()
        self.assertEqual(inbox, 'inbox')


class BaseMailTestMixin(object):

    ADDR = None
    PASSWORD = '6g8G6d%51'
    imap_cls = mail.IMAPAdapter

    host = None
    port = None
    ssl = None

    @classmethod
    def get_imap(cls):
        return cls.imap_cls(
            login=cls.ADDR, password=cls.PASSWORD, host=cls.host, port=cls.port,
            ssl=cls.ssl
        )

    @classmethod
    def setUpClass(cls):
        super(BaseMailTestMixin, cls).setUpClass()
        cls.imap = cls.get_imap()

    def get_inbox_msg(self):
        return {
            'folder': INBOX,
            'from': (u'Igor Katson', 'igor.katson@gmail.com'),
            'to': ('', self.ADDR),
            'subject': u'Привет Василий!',
            'text_re': u'Текст сообщения.*NovaCRM',
            'html_re': u'Текст сообщения.*<a.*href=.*NovaCRM',
            'date': datetime.date(2013, 11, 25)
    }

    def get_sent_msg(self):
        return {
            'folder': SENT,
            'from': (None, self.ADDR),
            'to': (None, 'igor.katson@gmail.com'),
            'subject': u'Привет Игорь!',
            'text_re': u'Текст сообщения.*NovaCRM',
            'html_re': u'Текст сообщения.*<a.*href=.*NovaCRM',
            'date': datetime.date(2013, 11, 25)
        }

    def test_get_inbox_folders(self):
        folder = self.imap.get_inbox_folder()
        self.assertIsInstance(folder, mail.IMAPFolder)

    def test_get_sent_folders(self):
        folders = self.imap.get_sent_folders()
        self.assertGreater(len(folders), 0)

        folder = self.imap.get_sent_folder()
        self.assertIsInstance(folder, mail.IMAPFolder)

    def test_get_trash_folders(self):
        folders = self.imap.get_trash_folders()
        self.assertGreater(len(folders), 0)

        folder = self.imap.get_trash_folder()
        self.assertIsInstance(folder, mail.IMAPFolder)

    def find_message(self, folder, msgdict, fail_on_not_found=True):
        self.imap.select(folder)
        since = msgdict['date'] - datetime.timedelta(1)
        before = msgdict['date'] + datetime.timedelta(1)
        subject = msgdict['subject']
        sender = msgdict['from'][1]
        result = None
        for i, msg in enumerate(
            self.imap.search_emails(
                sender=sender, since=since, before=before,
                subject=subject,
            )
        ):
            if i > 1:
                self.fail('More than 1 message found for %s' % msgdict)
            result = msg
        if fail_on_not_found and not result:
            self.fail('Cannot find message for %s' % msgdict)
        return result

    def _test_email_wrapper(self, msgdict, msg):
        self.assertEqual(msg.subject, msgdict['subject'])
        self.assertEqual(msg.date.date(), msgdict['date'])
        if msgdict['text_re']:
            self.assertRegexpMatches(
                msg.plaintext(),
                re.compile(msgdict['text_re'],
                           re.UNICODE | re.MULTILINE | re.DOTALL))
        if msgdict['html_re']:
            self.assertRegexpMatches(
                msg.html(), re.compile(msgdict['html_re'],
                                       re.UNICODE | re.MULTILINE | re.DOTALL))
        if msgdict['from'][0] is not None:
            self.assertEqual(msg.from_addr, msgdict['from'])
        else:
            self.assertEqual(msg.from_addr[1], msgdict['from'][1])
        if msgdict['to'][0] is not None:
            self.assertEqual(msg.to[0], msgdict['to'])
        else:
            self.assertEqual(msg.to[0][1], msgdict['to'][1])

    def test_inbox_msg(self):
        msgdict = self.get_inbox_msg()
        msg = self.find_message(
            self.imap.get_inbox_folder(), msgdict)
        self._test_email_wrapper(msgdict, msg)

    def test_sent_msg(self):
        msgdict = self.get_sent_msg()
        msg = self.find_message(
            self.imap.get_sent_folder(), msgdict)
        self._test_email_wrapper(msgdict, msg)

    def test_copy(self):
        copied = self.imap.copy()
        copied.select('INBOX')


class GmailTest(BaseMailTestMixin, unittest.TestCase):
    ADDR = 'novacrmtest@trip-travel.ru'
    imap_cls = mail.Gmail


class GmailAccessTokenTest(GmailTest, unittest.TestCase):
    # Test access with OAuth2 tokens.
    access_token = None
    refresh_token = '1/2ZPZPrdRAXj9eyODQFCZsWowL_9el4BBRQY69cgOXu4'
    url = 'https://accounts.google.com/o/oauth2/token'
    # The app is here:
    # https://cloud.google.com/console/project/apps~igor-katson-testing/
    client_id = ('1052104166572-j4i65n36to8n1meg20ogqo3g971ou7nj'
                 '.apps.googleusercontent.com')
    client_secret = 'Y2UuxHxkX0m4EEIHluCn8W0T'

    @classmethod
    def get_imap(cls):
        token = mail.Gmail.get_access_token(
            cls.refresh_token, cls.client_id, cls.client_secret)
        return cls.imap_cls(login=cls.ADDR, access_token=token['access_token'])


class GmailRefreshTokenTest(GmailAccessTokenTest):
    # Test that refresh token is used if access_token is missing or expired.
    @classmethod
    def get_imap(cls):
        return cls.imap_cls(
            login=cls.ADDR, access_token=cls.access_token,
            refresh_token=cls.refresh_token, client_id=cls.client_id,
            client_secret=cls.client_secret)


class YandexTest(BaseMailTestMixin, unittest.TestCase):
    ADDR = 'novacrmtest@yandex.ru'
    imap_cls = mail.YandexMail

    def get_sent_msg(self):
        # html not supported in yandex sent messages.
        result = super(YandexTest, self).get_sent_msg()
        result['html_re'] = None
        return result


class MailRuTest(BaseMailTestMixin, unittest.TestCase):
    ADDR = 'novacrmtest@mail.ru'
    imap_cls = mail.MailRuMail

    # Mail.ru does not support searching emails. So save all of them in memory
    # and search in memory.
    @classmethod
    def setUpClass(cls):
        super(MailRuTest, cls).setUpClass()
        cls.imap.select(cls.imap.get_inbox_folder())
        cls.inbox_msgs = list(cls.imap.search(limit=4))
        cls.imap.select(cls.imap.get_sent_folder())
        cls.sent_msgs = list(cls.imap.search(limit=4))

    def find_message(self, folder, msgdict, fail_on_not_found=False):
        if self.imap.inbox_folder_re.search(folder.name):
            msgs = self.inbox_msgs
        elif self.imap.sent_folder_re.search(folder.name):
            msgs = self.sent_msgs
        for msg in msgs:
            if msg.subject == msgdict['subject']:
                return msg
        if fail_on_not_found:
            self.fail('Cannot find mail.ru message for %s' % msgdict)


if __name__ == '__main__':
    unittest.main()