import pytest
import responses

import mano


@responses.activate
def test_studies(keyring, mock_studies_response):
    expected_studies = set([
        ('Project A', '123lrVdb0g6tf3PeJr5ZtZC8'),
        ('Project B', '123U93wwgS18aLDIwdYXTXsr')
    ])
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    studies = set()
    for study in mano.studies(keyring):
        studies.add(study)

    assert studies == expected_studies


@responses.activate
def test_users(keyring, mock_users_response):
    expected_users = set(["tgsidhm", "lholbc5", "yxzxtwr"])
    responses.post(
        keyring['URL'] + '/get-users/v1',
        body=mock_users_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    users = set()
    for user in mano.users(keyring, 'STUDY_ID'):
        users.add(user)
    assert users == expected_users


@responses.activate
def test_expand_study_id(keyring, mock_studies_response):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    expected_study = ('Project A', '123lrVdb0g6tf3PeJr5ZtZC8')
    study = mano.expand_study_id(keyring, '123lrVdb0g6tf3PeJr5ZtZC8')
    assert study == expected_study


@responses.activate
def test_expand_study_id_conflict(keyring, mock_studies_response):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(mano.AmbiguousStudyIDError):
        _ = mano.expand_study_id(keyring, '123')


@responses.activate
def test_expand_study_id_nomatch(keyring, mock_studies_response):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    study = mano.expand_study_id(keyring, '321')
    assert study is None


@responses.activate
def test_studyid(keyring, mock_studies_response):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    expected_studyid = '123lrVdb0g6tf3PeJr5ZtZC8'
    study_id = mano.studyid(keyring, 'Project A')
    assert study_id == expected_studyid


@responses.activate
def test_studyid_not_found(keyring, mock_studies_response):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(mano.StudyIDError):
        _ = mano.studyid(keyring, 'Project X')


@responses.activate
def test_studyname(keyring, mock_studies_response):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    expected_study_name = 'Project A'
    study_name = mano.studyname(keyring, '123lrVdb0g6tf3PeJr5ZtZC8')
    assert study_name == expected_study_name


@responses.activate
def test_studyname_not_found(keyring, mock_studies_response):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(mano.StudyNameError):
        _ = mano.studyname(keyring, 'x')
