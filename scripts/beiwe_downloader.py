#!/usr/bin/env python

import os
import mano
import logging
import mano.sync as msync
import argparse as ap

logger = logging.getLogger('downloader')
logging.basicConfig(level=logging.INFO)

def main():
    parser = ap.ArgumentParser('beiwe downloader script')
    parser.add_argument('--output-base', default='.')
    parser.add_argument('--backfill-start', default='2015-10-01T00:00:00')
    parser.add_argument('--keyring-section', default='beiwe.onnela')
    args = parser.parse_args()

    Keyring = mano.keyring(args.keyring_section)
    
    for study in mano.studies(Keyring):
        study_name,study_id = study
        for user_id in mano.users(Keyring, study_id):
            logger.info('downloading study=%s, user=%s', study_name, user_id)
            output_folder = os.path.join(args.output_base, study_name, user_id)
            msync.backfill(Keyring, study_id, user_id, output_folder, start_date=args.backfill_start)

if __name__ == '__main__':
    main()
