"""
Real API tests — hits the actual Beiwe server, requires a valid keyring.
Run with: pytest tests/test_real.py -s

This file is gitignored and should never be committed.
"""
import mano

STUDY_ID = "m4z54N5SU7Eqq2LbwmxQd2UN"

keyring = {
    "URL": "https://studies.beiwe.org",
    "ACCESS_KEY": "DWKHjy4oLyE2OQnigL7fvOaPQFc3rmQGsdM3ocVvdR02CRPQ4o53jnEWhiycX1ul",  # fill in
    "SECRET_KEY": "+eW8LZh0ya+aMbsgJykB6tuTEb2jZ579+tODQXnDovOQkThhqv3vi/VhgjFtmBys",  # fill in
    "USERNAME": "jackliu",
    "PASSWORD": "Lcm20021106!!!!!!!!!",
}


def test_fetch_accessible_studies_real():
    results = list(mano.fetch_accessible_studies(keyring))
    assert len(results) > 0
    for study_name, study_id in results:
        assert isinstance(study_name, str)
        assert isinstance(study_id, str)
        print(study_name, study_id)


def test_fetch_users_in_study_real():
    results = list(mano.fetch_users_in_study(keyring, STUDY_ID))
    assert isinstance(results, list)
    print(results)


def test_fetch_interventions_real():
    results = dict(mano.fetch_interventions(keyring, STUDY_ID))
    assert isinstance(results, dict)
    print(results)


def test_fetch_survey_history_real():
    results = dict(mano.fetch_survey_history(keyring, STUDY_ID))
    assert isinstance(results, dict)
    print(results)


def test_fetch_study_settings_real():
    results = dict(mano.fetch_study_settings(keyring, STUDY_ID))
    assert "device_settings" in results
    assert "surveys" in results
    assert "interventions" in results
    print(results)


def test_fetch_study_settings_test_real():
    results = dict(mano.fetch_study_settings_test(keyring, STUDY_ID))
    assert len(results) > 0
    assert "gps" in results
    print(results)


def test_fetch_participant_table_data_real():
    results = list(mano.fetch_participant_table_data(keyring, STUDY_ID))
    assert isinstance(results, list)
    print(results)


def test_fetch_participant_table_data_csv_real():
    results = list(mano.fetch_participant_table_data(keyring, STUDY_ID, data_format="csv"))
    assert len(results) == 1
    assert isinstance(results[0], str)
    print(results[0][:200])
