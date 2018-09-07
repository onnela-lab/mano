Mano
====
[![Build Status](https://travis-ci.org/harvard-nrg/mano.svg?branch=master)](https://travis-ci.org/harvard-nrg/mano)

Mano is a simple Python library that lets you write applications that interact 
with the [Beiwe Research Platform](https://www.hsph.harvard.edu/onnela-lab/beiwe-research-platform/). 
You can request lists of studies, users, device settings, download files (with or without encryption)
and more! (actually, not much more)

## Table of contents
1. [Requirements](#requirements)
2. [Mac OS X Notes](#mac-os-x-notes)
3. [Installation](#installation)
4. [Initial setup](#initial-setup)
5. [API for keyring access](#api-for-keyring-access)
6. [API for accessing study information](#api-for-accessing-study-information)
7. [API for downloading data](#api-for-downloading-data)

## Requirements
This software works with Python 2.6+ and 3 and has been tested on various 
flavors of macOS, Linux, and Linux Subsystem on Windows 10.
 
## macOS SSL note
I've encountered old versions of OpenSSL on some macOS distrubitions that cause 
issues interacting with Beiwe over HTTPS. The simplest solution I found was to 
install one of the Miniconda Python distributions which bundles a more recent 
version of OpenSSL 
([download link](http://conda.pydata.org/miniconda.html)).

## Installation
The simplest way to install `mano` is with `pip`

```bash
pip install mano
```

## Initial setup
To interact with Beiwe and download files you will need your Beiwe Research 
Platform `url`, `username`, `password`, `access key`, and `secret key` in a 
JSON file. Don't worry, we're going to eventually encrypt this file

```json
{
    "beiwe.onnela": {
        "URL": "...",
        "USERNAME": "...",
        "PASSWORD": "...",
        "ACCESS_KEY": "...",
        "SECRET_KEY": "..."
    }
}
```

> Note that you can also use environment variables `BEIWE_URL`, 
> `BEIWE_USERNAME`, `BEIWE_PASSWORD`, `BEIWE_ACCESS_KEY`, and 
> `BEIWE_SECRET_KEY` to store these variables and load your keyring using 
> `mano.keyring(None)`. You won't be able to use an environment variable for 
> storing study-specific secrets (described next). But depending on your 
> situation you may not even need study-specific secrets.

If you intend to use `mano` to encrypt certain downloaded data stream files at 
rest, you will want to add study-specific passphrases (which you're responsible 
for generating) to a special `SECRETS` section

```json
{
    "beiwe.onnela": {
        "URL": "...",
        "USERNAME": "...",
        "PASSWORD": "...",
        "ACCESS_KEY": "...",
        "SECRET_KEY": "...",
        "SECRETS": {
            "FAS Buckner": "...",
        }
    }
}
```

I'm guessing that you don't want this file sitting around in plain text, so for 
now this entire JSON blob **must** be passphrase protected using the `crypt.py` 
utility from the `cryptease` library which should be automatically installed along 
with the `mano` package

```bash
$ crypt.py --encrypt ~/.nrg-keyring.json --output-file ~/.nrg-keyring.enc
```

I'll leave it up to the reader to decide where to produce the encrypted version 
of this file, but I would highly recommend discarding the unencrypted version.

## API for keyring access
Before making any API calls, you need to read in your keyring file. The first 
parameter should be the name of the keyring section as shown above

```python
import mano

Keyring = mano.keyring('beiwe.onnela')
```

You can pass keyring passphrase as an argument to this function, or it will look 
for your keyring passphrase within a special `NRG_KEYRING_PASS` environment 
variable, or it will fallback on prompting you for the passphrase. This last 
strategy could cause non-interactive invocations to hang, so watch out.

## API for accessing study information
With your `Keyring` loaded, you can now access information about your studies, 
users (a.k.a. participants or subjects), and device settings using simple 
functions defined within the `mano` module

```python
for study in mano.studies(Keyring):
    print(study)

_,study_id = study # get the last printed study id

for user_id in mano.users(Keyring, study_id):
    print(user_id)

for setting in mano.device_settings(Keyring, study_id):
    print(setting)
```

## API for downloading data
With your `Keyring` loaded, you can also download data from your Beiwe server 
and extract it to your filesystem using the `mano.sync` module. And while we're 
at it, let's turn on more verbose logging so we can actually see what's 
happening

```python
import logging
import mano.sync as msync

logging.basicConfig(level=logging.INFO)

output_folder = '/tmp/beiwe-data'

zf = msync.download(Keyring, study_id, user_id, data_streams=['identifiers'])

zf.extractall(output_folder)
```

Notice that I passed `data_streams=['identifiers']` to `msync.download`. By 
default, that function will request *all* data for *all* data streams if you 
omit that parameter. Check out the [backfill](#backfill) section for more 
information.

The `msync.download` function will hand back a standard Python 
`zipfile.ZipFile` object which you can extract to the filesystem as shown 
above. Easy.

### encrypt files at rest
You can also pass the `ZipFile` object to `msync.save` if you wish to encrypt 
data stream files at rest

```python
lock_streams = ['gps', 'audio_recordings']

zf = msync.download(Keyring, study_id, user_id)

passphrase = Keyring['SECRETS']['FAS Buckner']

msync.save(Keyring, zf, user_id, output_folder, lock=lock_streams, passphrase=passphrase)
```

### backfill
By default `msync.download` will attempt to download *all* of the data for the 
specified `user_id` which could end up being prohibitively large either for 
you or the Beiwe server. For this reason, the `msync.download` function exposes 
parameters for `data_streams`, `time_start`, and `time_end`. Using these 
parameters you can download only certain data streams between certain start and 
end times

```python
data_streams = ['accel', 'ios_log', 'gps']

time_start = '2015-10-01T00:00:00'

time_end = '2015-12-01T00:00:00'

zf = msync.download(Keyring, study_id, user_id, data_streams=data_streams, time_start=time_start, time_end=time_end)

zf.extractall(output_folder)
```

Eventually you may find yourself day-dreaming about a `backfill` function that 
will slide a window from some aribitrary starting point to the present time in 
order to download all of your data in more digestible chunnks. You'll be happy 
to know that the `mano.sync` module already exposes a function for this

```python
start_date = '2015-01-01T00:00:00'

msync.backfill(Keyring, study_id, user_id, output_folder, start_date=start_date, lock=lock_streams, passphrase=passphrase)
```

Note that if you don't pass anything for the `lock` argument, you will not need 
`passphrase` either.

