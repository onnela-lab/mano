#!/usr/bin/env python

import argparse, logging
from os.path import join as pathjoin
from mano import load_keyring
from mano.sync import backfill
from mano.beiwe_api import fetch_accessible_studies, fetch_participants_in_study


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

    Keyring = load_keyring(args.keyring_section)

    for study in fetch_accessible_studies(Keyring):
        study_name, study_id = study
        for user_id in fetch_participants_in_study(Keyring, study_id):
            logger.info('downloading study=%s, user=%s', study_name, user_id)
            output_folder = pathjoin(args.output_base, study_name)
            backfill(Keyring, study_id, user_id, output_folder, start_date=args.backfill_start)


if __name__ == '__main__':
    main()
