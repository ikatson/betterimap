# betterimap, a Python IMAP client for humans.

[![Build Status](https://travis-ci.org/ikatson/betterimap.svg?branch=master)](https://travis-ci.org/ikatson/betterimap)

**betterimap** is a wrapper library for Python's standard ```imaplib```, that
improves the experience.

# Quickstart

### Print last 10 messages in the mailbox, with attachments

```python
imap = betterimap.IMAPAdapter(
    'username', 'password', host='imap.example.com', ssl=True)
    
imap.select(imap.get_inbox_folder())
 
### Download last 10 messages
for msg in imap.search(limit=10):
    
    print msg.subject  # prints unicode subject
    print msg.date  # prints a timezone-aware datetime.datetime object
    print msg.from_addr  # ('First Last', 'first.last@example.com')
    
    print msg.get_header('Date')  # get any unicode header
    
    print msg.to  # Prints receivers
    # [
    #    ('First Last2', 'first.last-2@example.com'),
    #    ('First Last3', 'first.last-3@example.com'),
    # ]
    
    print msg.html()  # prints html, if multipart
    print msg.plaintext()  # prints message plaintext
    
    
              
    for attachment in msg.attachments:
        print attachment.size # integer
        print attachment.data # the content of the attachment
        print attachment.filename # unicode
        print attachment.content_type # string
```

### Wait for new messages to come.

```python
imap = betterimap.IMAPAdapter(
    'username', 'password', host='imap.example.com', ssl=True)
stop, stream = imap.idle(copy=False)
 
for msg in stream:
    print msg

# When you are done, you can call stop(), to free the resources.    
stop()
```

### Search for existing messages

```python

imap = betterimap.IMAPAdapter(...)

# Search by subject
for msg in email.easy_search(subject=u'Some subject'):
    pass

# Search by date 
for msg in email.easy_search(exact_date=datetime.date(2014, 9, 27)):
    pass
        
# Search since and before 
for msg in email.easy_search(since=datetime.date(2014, 9, 27)):
    pass
for msg in email.easy_search(before=datetime.date(2014, 9, 27), limit=10):
    pass            
    
# Search by sender
for msg in email.easy_search(sender='123@example.com', limit=5):
    pass    
```

### Accessing Gmail with OAuth2

As Gmail forbids login/password access to IMAP, and only allows 
[OAuth2 access](https://developers.google.com/accounts/docs/OAuth2),
you will need an access token (short term use), and optionally a refresh token 
(for long term use) to login. To obtain them you will need:

- An application set up in [google developers console](https://console.developers.google.com/project)
- An access or refresh token given to this application, with scope ```https://mail.google.com/```

You can read [here](https://developers.google.com/accounts/docs/OAuth2) about 
how to do all this.

Once you have them, do something like:

```python

# If you have access token:
gmail = betterimap.Gmail(login='username@gmail.com', access_token=access_token)

# If you have refresh token:
gmail = betterimap.Gmail(
    login='username@gmail.com',
    access_token=access_token
    refresh_token=refresh_token,
    client_id=client_id,
    client_secret=client_secret,
    refresh_token_callback=refresh_callback  # optional
)
 
```

If ```refresh_token_callback``` is provided, it will be called with a dictionary
in format ```{'access_token': '...', 'expires_in': integer}```, so that you 
can update your storage with the refreshed access token.
