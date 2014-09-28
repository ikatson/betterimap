# coding: utf-8

import logging
import unittest

import betterimap

import mock

log = logging.getLogger(__name__)


class IMAPAdapterStub(betterimap.IMAPAdapter):
    """A fake IMAPAdapter."""
    imap_cls = mock.Mock()
    imap_cls_ssl = mock.Mock()

    def __init__(self, *args, **kwargs):
        super(IMAPAdapterStub, self).__init__('user', 'password', host='host')


# TODO(igor): write more tests here..
class IMAPAdapterTest(unittest.TestCase):

    def testGetInboxFolderChoosesCorrectResultIfAmbiguous(self):

        imap = IMAPAdapterStub()
        ambiguous_inbox_dirs = [
            betterimap.IMAPFolder(u'() "." "INBOX.Spam"'),
            betterimap.IMAPFolder(u'() "." "INBOX"'),
        ]
        with mock.patch.object(imap, 'list', lambda: ambiguous_inbox_dirs):
            inbox = imap.get_inbox_folder()
        self.assertEqual(inbox.name, 'INBOX')

    def testGetInboxFolderReturnsStringIfNoInboxFolderFound(self):

        no_inbox_folder = [
            betterimap.IMAPFolder(u'() "." "SomeFolder"'),
            betterimap.IMAPFolder(u'() "." "SomeOtherFolder"'),
        ]
        imap = IMAPAdapterStub()
        with mock.patch.object(imap, 'list', lambda: no_inbox_folder):
            inbox = imap.get_inbox_folder()
        self.assertEqual(inbox, 'inbox')


