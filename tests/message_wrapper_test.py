# coding: utf-8

import datetime
import email.message
import os

import mock
import pytz

import betterimap

from . import base


class MessageWrapperTest(base.BaseMockTest):

    testcls = betterimap.MessageWrapper

    # Testing core internal methods first.

    EDT = pytz.timezone('US/Eastern')

    UNICODE_MSG = u'Длинное сообщение'

    def testParseDateReturnsAwareDateTimeIfTimezoneProvided(self):
        dt = 'Sun, 28 Sep 2014 00:00:06 -0400 (EDT)'
        expected = self.EDT.localize(datetime.datetime(2014, 9, 28, 0, 0, 6))
        self.assertEqual(self.testcls.parse_date(dt), expected)

    def testParseDateReturnsAwareDateTimeInUTCIfTimezoneNotProvided(self):
        dt = 'Sun, 28 Sep 2014 00:00:06'
        expected = pytz.utc.localize(datetime.datetime(2014, 9, 28, 0, 0, 6))
        self.assertEqual(self.testcls.parse_date(dt), expected)

    def testParseDateReturnsNaiveDateTimeIfTimezoneNotProvidedAndDefaultTzIsNone(self):
        dt = 'Sun, 28 Sep 2014 00:00:06'
        expected = datetime.datetime(2014, 9, 28, 0, 0, 6)
        self.assertEqual(self.testcls.parse_date(dt, default_tz=None), expected)

    def testParseDateReturnsNoneIfInvalidData(self):
        for bad_data in ('garbage', '', None):
            self.assertIsNone(self.testcls.parse_date(bad_data))

    def testGetHeaderTriesEncodingsInBadEncodingList(self):
        bad_encoding_name = 'bad-encoding-name'
        self.patch('betterimap.MessageWrapper.BAD_ENCODING_MAP', {
            bad_encoding_name: 'cp1251'
        })
        self.patch('betterimap.chardet', None)
        header = [(self.UNICODE_MSG.encode('cp1251'), bad_encoding_name)]
        self.patch('email.header.decode_header').return_value = header

        result = self.testcls._get_header('unused value')

        self.assertEqual(result, [self.UNICODE_MSG])

    def testGetHeaderTriesLastResortEncodingsIfEncodingUnknown(self):
        self.patch(
            'betterimap.MessageWrapper.LAST_RESORT_ENCODINGS', ['koi8-r'])
        self.patch('betterimap.chardet', None)
        # There's an encoding mismatch here.
        header = [(self.UNICODE_MSG.encode('koi8-r'), 'utf-8')]
        self.patch('email.header.decode_header').return_value = header

        result = self.testcls._get_header('unused value')

        self.assertEqual(result, [self.UNICODE_MSG])

    def testGetHeaderTriesChardetIfItIsAvailable(self):
        # No last resort encodings, and no encoding returned
        # by email.header.decode_header, but chardet available.
        self.patch('betterimap.MessageWrapper.LAST_RESORT_ENCODINGS', [])
        header = [(self.UNICODE_MSG.encode('koi8-r'), '')]
        self.patch('email.header.decode_header').return_value = header
        self.assertIsNotNone(betterimap.chardet)

        result = self.testcls._get_header('unused value')

        self.assertEqual(result, [self.UNICODE_MSG])

    def testGetHeaderReturnsUnicodeEvenWithWorstData(self):
        # No chardet, no last resort encodings, and no encoding returned
        # by email.header.decode_header.
        self.patch('betterimap.MessageWrapper.LAST_RESORT_ENCODINGS', [])
        self.patch('betterimap.chardet', None)
        header = [(self.UNICODE_MSG.encode('koi8-r'), '')]
        self.patch('email.header.decode_header').return_value = header

        result = self.testcls._get_header('unused value')

        self.assertIsInstance(result[0], unicode)
        self.assertEqual(result, [u' '])

    def testParseAddrListReturnsCorrectResult(self):
        msg = email.message.Message()
        msg['From'] = '<anybody@gmail.com>,=?UTF-8?B?0JjQs9C+0YDRjCDQr9C60L7QstC70LXQsg==?= <address@gmail.com>'
        msg = self.testcls(msg)
        self.assertEqual(
            msg._parse_addrlist('From'),
            [('', 'anybody@gmail.com'), (u'Игорь Яковлев', 'address@gmail.com')]
        )


class Email1Test(base.BaseMockTest):

    filename = os.path.join(os.path.dirname(__file__), 'data', 'em1.eml')
    from_addr = (u'Igor Katson', u'addr1@gmail.com')
    to_addrs = [
        (u'Igor Katson', u'addr1@gmail.com'), (u'Galina', u'addr2@gmail.com')]
    subject = u'Тестовое письмо'
    plaintext = u'Текст, а также *HTML*\r\n'
    html = u'<div dir="ltr">Текст, а также <b>HTML</b></div>\r\n'
    date = pytz.timezone('US/Pacific').localize(
        datetime.datetime(2014, 9, 28, 0, 7, 13))
    received = date
    attachments = {
        'test.txt': {
            'data': 'Some text\n',
            'content_type': 'text/plain',
            'size': 10
        },
        'pixel.png': {
            'content_type': 'image/png',
            'size': 95
        }
    }

    @classmethod
    def setUpClass(cls):
        with open(cls.filename) as f:
            cls.content = f.read()
        cls.msg = betterimap.MessageWrapper(
            email.message_from_string(cls.content))

    def testFrom(self):
        self.assertEqual(self.msg.from_addr, self.from_addr)

    def testSubject(self):
        self.assertEqual(self.msg.subject, self.subject)

    def testToAddres(self):
        self.assertEqual(self.msg.to, self.to_addrs)

    def testDate(self):
        self.assertEqual(self.msg.date, self.date)

    def testReceived(self):
        self.assertEqual(self.msg.received, self.received)

    def testPlaintext(self):
        self.assertEqual(self.msg.plaintext(), self.plaintext)

    def testHtml(self):
        self.assertEqual(self.msg.html(), self.html)

    def testAttachments(self):
        for attachment in self.msg.attachments():
            expected = self.attachments[attachment.filename]
            if 'size' in expected:
                self.assertEqual(attachment.size, expected['size'])
            if 'content_type' in expected:
                self.assertEqual(
                    attachment.content_type, expected['content_type'])
            if 'data' in expected:
                self.assertEqual(attachment.data, expected['data'])

