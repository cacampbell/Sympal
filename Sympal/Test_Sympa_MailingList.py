#!/usr/bin/env python3
from os import environ
from unittest import TestCase
from unittest import TestLoader
from unittest import TextTestRunner

from Sympal.Sympa import Sympa


class Test_Sympa_MailingList(TestCase):
    def setUp(self):
        self.sympa = Sympa(environ['sympa_url'])
        self.sympa.log_in(environ['admin_email'], environ['admin_pass'])

    def test_print_lists(self):
        for name, l in self.sympa.lists.items():
            print("Name: {}, List: {}".format(name, l))

    def test_populate_all(self):
        self.sympa.populate_all()

    def test_get_subscribers(self):
        for name, l in self.sympa.lists.items():
            print("Subscribers for list '{}'".format(name))
            subscribers = l.get_subscribers()
            if subscribers:
                for email, sub in subscribers.items():
                    print("Email: {}, Name: {}".format(email, sub.name))

    def test_get_bouncing(self):
        for name, l in self.sympa.lists.items():
            print("Bouncing for list '{}'".format(name))
            bouncing = l.get_bouncing()
            if bouncing:
                print(bouncing)

    def test_get_subscribers_email_list(self):
        for name, l in self.sympa.lists.items():
            print("Subscribers email list for '{}'".format(name))
            email_list = l.get_subscribers_email_list()
            if email_list:
                for email in email_list:
                    print("Email: {}".format(email))

    def test_get_bouncing_email_list(self):
        for name, l in self.sympa.lists.items():
            print("Bouncing email list for '{}'".format(name))
            email_list = l.get_bouncing_email_list()
            if email_list:
                for email in email_list:
                    print("Email: {}".format(email))

    def test_add_subscriber(self):
        subscriber = "cacampbell@ucdavis.edu"
        listname = environ['default_list']
        self.sympa.lists[listname].add_subscriber(subscriber)

    def test_remove_subscriber(self):
        subscriber = "cacampbell@ucdavis.edu"
        listname = environ['default_list']
        self.sympa.lists[listname].remove_subscriber(subscriber)

    def test_set_subscribers(self):
        email_list = environ["test_email_list"]
        self.sympa.lists[environ['default_list']].set_subscribers(email_list)

    def tearDown(self):
        self.sympa.log_out()
        self.sympa.close()


if __name__ == "__main__":
    suite = TestLoader().loadTestsFromTestCase(Test_Sympa_MailingList)
    TextTestRunner(verbosity=3).run(suite)
