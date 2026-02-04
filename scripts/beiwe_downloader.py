#!/usr/bin/env python

import argparse
import logging
import os

import mano
import mano.sync as msync

"""
Executable script to download Beiwe study data for all users in all studies using backfill
"""


logger = logging.getLogger('downloader')
logging.basicConfig(level=logging.INFO)


def main():
    parser = argparse.ArgumentParser('beiwe downloader script')
    parser.add_argument('--output-base', default='.')
    parser.add_argument('--backfill-start', default='2022-02-15T00:00:00')
    parser.add_argument('--keyring-section', default='beiwe.onnela')
    args = parser.parse_args()

    Keyring = mano.load_keyring(args.keyring_section)

    for study in mano.fetch_accessible_studies(Keyring):
        study_name, study_id = study
        for user_id in mano.fetch_users_in_study(Keyring, study_id):
            logger.info('downloading study=%s, user=%s', study_name, user_id)
            output_folder = os.path.join(args.output_base, study_name)
            msync.backfill(Keyring, study_id, user_id, output_folder, start_date=args.backfill_start)


if __name__ == '__main__':
    main()
