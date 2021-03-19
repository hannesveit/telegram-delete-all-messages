"""Run some functional tests against the telegram test servers.

* All tests use the same module-level apps, so we need to auth only once.

* The wait times are pretty generous, to avoid flood wait exceptions. If you
  run the tests many times in a row, you may still be banned. Most likely,
  only your dummy user (other_guy) will be affected, since he's the one
  creating channels and inviting you to groups too frequently. In this case,
  you can simply delete the `test_other.session` file and rerun to circumvent
  the wait.

* Not testing deleting large amounts of messages to avoid flood wait exceptions
  for too frequent send_message().

* Couldn't make it work with two anonymous users (99966XYYYY) -- can't import
  contact of test users by phone number, and adding by user ID (via add_contact
  in pyrogram >=1.2.0) doesn't work either. Looks like one account (app) needs
  to be real, but app_2 can use a test account.
"""

import io
import os.path
import random
import string
import sys
import unittest
from datetime import datetime
from time import sleep

from pyrogram.types import InputPhoneContact

from cleaner import Cleaner, start_app

# constants
MAIN_SESSION = 'test_main'
OTHER_SESSION = 'test_other'

# global apps and users, used by all tests
app = None
app_2 = None
me = None
other_guy = None


def setUpModule():
    global app
    global app_2
    global me
    global other_guy

    # start main session
    sys.stderr.write('Logging into telegram test server...\n\n')
    app = start_app(MAIN_SESSION, test_mode=True, force_sms=True)

    # start dummy user session
    sys.stderr.write('Logging in another dummy user to group-chat with')
    new_session = not os.path.isfile(f'{OTHER_SESSION}.session')
    if new_session:
        sys.stderr.write(
            ' (when prompted, enter any first name)')
    sys.stderr.write('...\n\n')

    phone_number, phone_code = random_test_phone_credentials()
    app_2 = start_app(
        OTHER_SESSION,
        test_mode=True,
        phone_number=phone_number,
        phone_code=phone_code,
    )

    # store users globally so we need to fetch them only once
    me = app.get_me()
    other_guy = app_2.get_me()

    # add main user to dummy user's contacts so it can initiate group chat
    try:
        app_2.import_contacts([InputPhoneContact(me.phone_number, 'Bob')])
    except AttributeError:
        # pyrogram < 1.2.0
        app_2.add_contacts([InputPhoneContact(me.phone_number, 'Bob')])

    # prevent CHAT_INVALID in new sessions
    if new_session:
        sys.stderr.write(
            'New session detected -- waiting 60s to prevent CHAT_INVALID '
            'on group chat creation. This won\'t be necessary going forward, '
            f'unless you delete the {OTHER_SESSION}.session file.\n\n')
        sleep(60)


def tearDownModule():
    # clean up after ourselves
    app_2.delete_contacts(me.id)
    # give apps some time to finish async business to prevent exceptions
    sleep(15)
    app.stop()
    app_2.stop()


class CommonTestsMixin:

    def test_default_args_delete_10_messages(self):
        self.send_random_messages(10)
        self.assertEqual(len(self.messages_by(me)), 10)
        Cleaner(app, chats=[self.chat]).run()
        sleep(2)
        self.assertEqual(len(self.messages_by(me)), 0)

    def test_search_chunk_size_3_delete_7_messages(self):
        self.send_random_messages(7)
        self.assertEqual(len(self.messages_by(me)), 7)
        Cleaner(app, chats=[self.chat], search_chunk_size=3).run()
        sleep(2)
        self.assertEqual(len(self.messages_by(me)), 0)

    def test_delete_chunk_size_2_delete_5_messages(self):
        self.send_random_messages(5)
        self.assertEqual(len(self.messages_by(me)), 5)
        Cleaner(app, chats=[self.chat], delete_chunk_size=2).run()
        sleep(2)
        self.assertEqual(len(self.messages_by(me)), 0)

    def test_not_trying_to_delete_foreign_messages(self):
        app_2.send_message(self.chat.id, 'hello world')
        # in groups, creators have 1 indelible message that they created the
        # group, so other_guy now has 1 (supergroup) or 2 (group) messages
        count_before = len(self.messages_by(other_guy))
        self.assertTrue(count_before in (1, 2))
        Cleaner(app, chats=[self.chat]).run()
        sleep(2)
        self.assertEqual(len(self.messages_by(other_guy)), count_before)

    def send_random_messages(self, n):
        for _ in range(n):
            app.send_message(self.chat.id, random_text())
            sleep(0.2)
        sleep(1)

    def messages_by(self, user):
        return app.search_messages(self.chat.id, from_user=user.id)


class TestCleanerOnGroups(unittest.TestCase, CommonTestsMixin):

    def setUp(self):
        self.chat = app_2.create_group(f'TEST_GROUP_{now()}', [me.id])
        sleep(10)

    def tearDown(self):
        app_2.leave_chat(self.chat.id, delete=True)
        sleep(3)


class TestCleanerOnSuperGroups(unittest.TestCase, CommonTestsMixin):

    def setUp(self):
        self.chat = app_2.create_supergroup(f'TEST_SUPERGROUP_{now()}', '')
        sleep(10)
        app_2.add_chat_members(self.chat.id, me.id)
        sleep(3)

    def tearDown(self):
        app_2.delete_supergroup(self.chat.id)
        sleep(3)


def now():
    return datetime.now().strftime('%Y-%m-%d_%H:%M:%S.%f')


def random_text():
    return ''.join(
        random.choice(string.ascii_lowercase + (3 * '. '))
        for _ in random.randint(3, 30) * ' ')


def random_test_phone_credentials(dc=1):
    # https://docs.pyrogram.org/topics/test-servers#test-numbers
    rnd_4_digits = ''.join(random.choice('0123456789') for _ in range(4))
    number = f'99966{dc}{rnd_4_digits}'
    code = 5 * str(dc)
    return number, code


if __name__ == '__main__':
    unittest.main(verbosity=2)
