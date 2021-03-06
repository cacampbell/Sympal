###Sympal

####pip3 install Sympal

A python3 API for basic administration tasks for Sympa mailing lists.

This package is NOT meant to replace the server side command line interface for
Sympa, but instead, is a management tool for users of an institutional Sympa
server. With this package, you will be able to manage list subscriptions and
bounces of your mailing lists with ease.

I mostly wrote this because the Sympa web interface is clunky -- being able to
script complex changes to lists saves me a lot of time.

    with Sympa("http://lists.server.domain/sympa") as sympa:
        sympa.log_in("email", "password")

        sympa.populate_all()  # Can populate all lists at once, but don't have to do so

        for name, mailing_list in sympa.lists.items():
            print("Name: {}".format(name))

            print("Subscribers:")  # All subscribed email addresses
            for email, subscriber in mailing_list.get_subscribers().items():
                print("{}".format(email))

            print("Bouncing:")  # Bouncing email addresses
            for email, subscriber in mailing_list.get_bouncing().items():
                print("{}".format(email))

            # Reset bouncing email addresses
            mailing_list.reset_bouncing()

            # Remove bouncing email addresses
            mailing_list.remove_bouncing()

            # Add example user
            mailing_list.add_subscriber("user@example.com", "Firstname Lastname")

            # Remove example user
            mailing_list.remove_subscriber("user@example.com")

            # Set the subscribers to the list of 3 example addresses
            mailing_list.set_subscribers(["example1@example.com",
                                   "example2@example.com",
                                   "example3@example.com"])

            # Set subscribers to those contained in test_email_list.txt
            mailing_list.set_subscribers("test_email_list.txt")


Alternatively, you can also create a Sympa object without context management:

    sympa = Sympa("http://lists.server.domain/sympa")
    sympa.log_in("email", "password")  # Log in
    ...
    subscribers = sympa.lists['list_name'].get_subscribers()  # Do things
    ...
    sympa.log_out()  # log out - normally called by __exit__
    sympa.close()  # close connection - normally called by __exit__
