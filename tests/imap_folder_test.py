# coding: utf-8

import unittest
import betterimap


class IMAPFolderTest(unittest.TestCase):

    def testFlagsAreParsedCorrectly(self):
        fld = betterimap.IMAPFolder(
            ur'(\\HasNoChildren \\Sent \\Sent) "." "Sent Folder"')
        self.assertEqual(fld.name, u'Sent Folder')
        self.assertEqual(fld.flags, set(['HasNoChildren', 'Sent']))

    def testFlagsAreParsedCorrectlyIfNoFlags(self):
        fld = betterimap.IMAPFolder(
            u'() "." "Sent Folder"')
        self.assertEqual(fld.flags, set())

    def testUtf7NameAndFlagsDecodedCorrectly(self):
        fld = betterimap.IMAPFolder(
            r'(\\Unmarked \\HasNoChildren \\Sent) "|" '
            '"&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-"'
        )
        self.assertEqual(fld.name, u'Отправленные')
        self.assertEqual(
            fld.flags, set(['Unmarked', 'HasNoChildren', 'Sent']))
