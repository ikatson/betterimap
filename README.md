# betterimap, a Python IMAP client for humans.

>> THIS IS WORK IN PROGRESS

**betterimap** is a wrapper library for Python's standard ```imaplib```, that
improves the experience.

# Quickstart

## Print last 10 messages in the mailbox, with attachments

```python
import betterimap

imap = betterimap.IMAPAdapter(
    'username', 'password', host='imap.example.com', ssl=True)
    
imap.select(imap.get_inbox_folder())    

# Download last 10 messages
for msg in imap.search(limit=10):
    print msg.subject
    # prints unicode subject
    
    print msg.date
    # prints a timezone-aware datetime.datetime object

    print msg.from
    # ('First Last', 'first.last@example.com')
    
    print msg.to
    # [
        ('First Last', 'first.last@example.com')
      ]
              
    for attachment in msg.attachments:
        print attachment.size # integer
        print attachment.data # the content of the attachment
        print attachment.filename # unicode
        print attachment.content_type # string
```

## Wait for new messages to come.

```python
import betterimap

imap = betterimap.IMAPAdapter(
    'username', 'password', host='imap.example.com', ssl=True)
stop, stream = imap.idle(copy=False)
 
for msg in stream:
    print msg
    
stop()
```
