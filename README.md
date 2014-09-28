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


### Gmail with OAuth2

```
