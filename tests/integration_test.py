# coding: utf-8
"""Test integration with real-world IMAP servers."""


import datetime
import logging
import os
import re
import unittest

import betterimap


log = logging.getLogger(__name__)

INBOX = 0
SENT = 1


class BaseIntegrationTestMixin(object):

    ADDR = None
    PASSWORD = os.environ['BASE_EMAIL_PASSWORD']
    imap_cls = betterimap.IMAPAdapter

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
        super(BaseIntegrationTestMixin, cls).setUpClass()
        cls.imap = cls.get_imap()

    def get_inbox_msg(self):
        return {
            'folder': INBOX,
            'from': (u'Igor Katson', os.environ['FROM_ADDR']),
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
            'to': (None, os.environ['FROM_ADDR']),
            'subject': u'Привет Игорь!',
            'text_re': u'Текст сообщения.*NovaCRM',
            'html_re': u'Текст сообщения.*<a.*href=.*NovaCRM',
            'date': datetime.date(2013, 11, 25)
        }

    def test_get_inbox_folders(self):
        folder = self.imap.get_inbox_folder()
        self.assertIsInstance(folder, betterimap.IMAPFolder)

    def test_get_sent_folders(self):
        folders = self.imap.get_sent_folders()
        self.assertGreater(len(folders), 0)

        folder = self.imap.get_sent_folder()
        self.assertIsInstance(folder, betterimap.IMAPFolder)

    def test_get_trash_folders(self):
        folders = self.imap.get_trash_folders()
        self.assertGreater(len(folders), 0)

        folder = self.imap.get_trash_folder()
        self.assertIsInstance(folder, betterimap.IMAPFolder)

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


class GmailTest(BaseIntegrationTestMixin, unittest.TestCase):
    ADDR = os.environ['GMAIL_ADDR']
    imap_cls = betterimap.Gmail


class GmailAccessTokenTest(GmailTest, unittest.TestCase):
    # Test access with OAuth2 tokens.
    access_token = None
    refresh_token = os.environ['GMAIL_OAUTH_REFRESH_TOKEN']
    url = 'https://accounts.google.com/o/oauth2/token'
    client_id = os.environ['GMAIL_OAUTH_SECRET_KEY']
    client_secret = os.environ['GMAIL_OAUTH_SECRET_KEY']

    @classmethod
    def get_imap(cls):
        token = betterimap.Gmail.get_access_token(
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


class YandexTest(BaseIntegrationTestMixin, unittest.TestCase):
    ADDR = os.environ['YANDEX_ADDR']
    imap_cls = betterimap.YandexMail

    def get_sent_msg(self):
        # html not supported in yandex sent messages.
        result = super(YandexTest, self).get_sent_msg()
        result['html_re'] = None
        return result


class MailRuTest(BaseIntegrationTestMixin, unittest.TestCase):
    ADDR = os.environ['MAILRU_ADDR']
    imap_cls = betterimap.MailRuMail

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
