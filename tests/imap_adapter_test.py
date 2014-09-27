# coding: utf-8

import logging
import unittest
import betterimap

log = logging.getLogger(__name__)


class IMAP4Stub(object):
    """A test-only stub for IMAP4."""

    def __init__(self, *args, **kwargs):
        return

    def login(self, *args, **kwargs):
        return


class IMAPAdapterStub(betterimap.IMAPAdapter):
    """A stub for IMAPAdapter that """
    imap_cls = IMAP4Stub
    imap_cls_ssl = IMAP4Stub

    def __init__(self, *args, **kwargs):
        super(IMAPAdapterStub, self).__init__('user', 'password', host='host')


class IMAPAdapterTest(unittest.TestCase):

    class IMAPAdapterAmbiguousInboxStub(IMAPAdapterStub):
        def list(self):
            return [
                betterimap.IMAPFolder(u'() "." "INBOX.Spam"'),
                betterimap.IMAPFolder(u'() "." "INBOX"'),
            ]

    class IMAPAdapterNoInboxStub(IMAPAdapterStub):
        def list(self):
            return [
                betterimap.IMAPFolder(u'() "." "SomeFolder"'),
                betterimap.IMAPFolder(u'() "." "SomeOtherFolder"'),
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


