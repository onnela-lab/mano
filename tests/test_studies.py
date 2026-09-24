import pytest
import responses

from mano import (AmbiguousStudyIDError, StudyIDError, StudyNameError, expand_study_id,
    fetch_accessible_studies, fetch_users_in_study, studyid, studyname)
from mano.constants import APIError


@responses.activate
def test_studies(keyring: dict[str, str], mock_studies_response: str):
    expected_studies = {
        ('Project A', '123lrVdb0g6tf3PeJr5ZtZC8'),
        ('Project B', '123U93wwgS18aLDIwdYXTXsr')
    }
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    studies = set[tuple[str, str]]()
    for study in fetch_accessible_studies(keyring):
        studies.add(study)
    
    assert studies == expected_studies


@responses.activate
def test_expand_study_id(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    expected_study = ('Project A', '123lrVdb0g6tf3PeJr5ZtZC8')
    study = expand_study_id(keyring, '123lrVdb0g6tf3PeJr5ZtZC8')
    assert study == expected_study


@responses.activate
def test_expand_study_id_conflict(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(AmbiguousStudyIDError):
        _ = expand_study_id(keyring, '123')


@responses.activate
def test_expand_study_id_nomatch(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    study = expand_study_id(keyring, '321')
    assert study is None


@responses.activate
def test_studyid(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    expected_studyid = '123lrVdb0g6tf3PeJr5ZtZC8'
    study_id = studyid(keyring, 'Project A')
    assert study_id == expected_studyid


@responses.activate
def test_studyid_not_found(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(StudyIDError):
        _ = studyid(keyring, 'Project X')


@responses.activate
def test_studyname(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    expected_study_name = 'Project A'
    study_name = studyname(keyring, '123lrVdb0g6tf3PeJr5ZtZC8')
    assert study_name == expected_study_name


@responses.activate
def test_studyname_not_found(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(StudyNameError):
        _ = studyname(keyring, 'x')


@responses.activate
def test_fetch_accessible_studies_empty_response(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body='{}',
        status=200,
        content_type='text/html; charset=utf-8'
    )
    results = list(fetch_accessible_studies(keyring))
    assert results == []


@responses.activate
def test_fetch_accessible_studies_http_error_raises_api_error(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body='Internal Server Error',
        status=500,
    )
    with pytest.raises(APIError, match=r"^response not ok \(500\) https://studies.beiwe.org/get-studies/v1$"):
        list(fetch_accessible_studies(keyring))


@responses.activate
def test_whether_credentials_are_passed(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body='{}',
        status=200,
        content_type='text/html; charset=utf-8'
    )
    list(fetch_accessible_studies(keyring))

    request_body = responses.calls[0].request.body
    assert request_body is not None
    assert 'access_key=ACCESS_KEY' in str(request_body)
    assert 'secret_key=SECRET_KEY' in str(request_body)



@responses.activate
def test_studyid_case_sensitive(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(StudyIDError):
        studyid(keyring, 'project a')


@responses.activate
def test_studyname_case_sensitive(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(StudyNameError):
        studyname(keyring, '123LRVDB0G6TF3PEJR5ZTZCB')


@responses.activate
def test_studyid_empty_string_raises_study_id_error(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(StudyIDError):
        studyid(keyring, '')


@responses.activate
def test_studyname_empty_string_raises_study_name_error(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(StudyNameError):
        studyname(keyring, '')


@responses.activate
def test_studyid_duplicate_study_names_returns_first_match(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body='{"id_first": "Same Name", "id_second": "Same Name"}',
        status=200,
        content_type='text/html; charset=utf-8'
    )
    result = studyid(keyring, 'Same Name')
    assert result == 'id_first'


@responses.activate
def test_fetch_users_in_study_empty_list_yields_nothing(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-participants/v1',
        body='[]',
        status=200,
        content_type='text/html; charset=utf-8'
    )
    results = list(fetch_users_in_study(keyring, 'STUDY_ID'))
    assert results == []

# Test exact matching, the way it currently works.
@responses.activate
def test_studyid_with_whitespace_name_not_found(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(StudyIDError):
        studyid(keyring, ' Project A ')
