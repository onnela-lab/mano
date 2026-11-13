import pytest, responses

from mano import (AmbiguousStudyIDError, expand_study_id, fetch_accessible_studies,
    fetch_users_in_study, studyid, StudyIDError, studyname, StudyNameError)
from mano.constants import APIError


# Listing the studies a user can access is the first step of most workflows, and names must pair
# with the right IDs.
@responses.activate
def test_fetch_accessible_studies_returns_name_and_id_pairs(keyring: dict[str, str], mock_studies_response: str):
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


# Users can give a short ID prefix, and it must expand to the full study.
@responses.activate
def test_expand_study_id_expands_unique_prefix(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    expected_study = ('Project A', '123lrVdb0g6tf3PeJr5ZtZC8')
    study = expand_study_id(keyring, '123lrVdb0g6tf3PeJr5ZtZC8')
    assert study == expected_study


# A prefix that fits two studies must raise an error, so the user never gets the wrong study's data.
@responses.activate
def test_expand_study_id_ambiguous_prefix_raises(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(AmbiguousStudyIDError):
        _ = expand_study_id(keyring, '123')


# A prefix that matches nothing must return None so callers can tell it apart from an error.
@responses.activate
def test_expand_study_id_unknown_prefix_returns_none(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    study = expand_study_id(keyring, '321')
    assert study is None


# Users know study names, not IDs, and the lookup must return the right ID.
@responses.activate
def test_studyid_returns_id_for_exact_name(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    expected_studyid = '123lrVdb0g6tf3PeJr5ZtZC8'
    study_id = studyid(keyring, 'Project A')
    assert study_id == expected_studyid


# A near-miss name must not silently pick a different study.
# This is a parametrized test: pytest runs it once for each case listed in the decorator below,
# passing that case's values in as the test function's arguments.
# Checks that studyid() raises StudyIDError when no study has the given name.
# studyid() needs an exact match, so every value below should miss. The mock server knows two
# studies, "Project A" and "Project B". This test runs once per value in the list.
@pytest.mark.parametrize(
    "name",
    [
        "Project X",     # a name that doesn't exist
        "project a",     # a real name, but lowercase
        "",              # empty string
        " Project A ",   # a real name with spaces around it
    ],
    ids=["unknown_name", "wrong_case", "empty_string", "surrounding_whitespace"],
)
@responses.activate
def test_studyid_not_found(keyring: dict[str, str], mock_studies_response: str, name: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(StudyIDError):
        studyid(keyring, name)


# Users often have only an ID, and the lookup must return the matching name.
@responses.activate
def test_studyname_returns_name_for_id(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    expected_study_name = 'Project A'
    study_name = studyname(keyring, '123lrVdb0g6tf3PeJr5ZtZC8')
    assert study_name == expected_study_name


# A near-miss ID must not silently pick a different study.
# This is a parametrized test: pytest runs it once for each case listed in the decorator below,
# passing that case's values in as the test function's arguments.
# Checks that studyname() raises StudyNameError when no study has the given ID.
# studyname() needs an exact match, so every value below should miss. The mock server knows the
# ID `123lrVdb0g6tf3PeJr5ZtZC8` ("Project A"). This test runs once per value in the list.
@pytest.mark.parametrize(
    "sid",
    [
        "x",                          # an ID that doesn't exist
        "",                           # empty string
        "123LRVDB0G6TF3PEJR5ZTZC8",   # the real Project A ID in uppercase: misses only because
                                      # the lookup is case-sensitive
    ],
    ids=["unknown_id", "empty_string", "wrong_case"],
)
@responses.activate
def test_studyname_not_found(keyring: dict[str, str], mock_studies_response: str, sid: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(StudyNameError):
        studyname(keyring, sid)


# A user with no studies is normal and must give an empty result, not an error.
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


# The exact message is what users see, so it needs the status code and URL.
@responses.activate
def test_fetch_accessible_studies_http_error_raises_api_error(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body='Internal Server Error',
        status=500,
    )
    with pytest.raises(APIError, match=r"^response not ok \(500\) https://studies.beiwe.org/get-studies/v1$"):
        list(fetch_accessible_studies(keyring))


# The server rejects requests without the keys, so they must be in the POST body.
@responses.activate
def test_fetch_accessible_studies_sends_credentials(keyring: dict[str, str]):
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



# Study names are not unique on the server, so the lookup must behave predictably when two share a
# name.
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


# Not a duplicate: fetch_users_in_study is the backward-compatible alias of
# fetch_participants_in_study. This test checks that the alias is still exported and still
# behaves the same; test_unit_tests.py tests the empty list against the current name.
@responses.activate
def test_fetch_users_in_study_empty_list_yields_nothing(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-participant-ids/v1',
        body='[]',
        status=200,
        content_type='text/html; charset=utf-8'
    )
    results = list(fetch_users_in_study(keyring, 'STUDY_ID'))
    assert results == []


#
# lookups against a keyring with no accessible studies
#


EMPTY_STUDIES_RESPONSE = '{}'


# A new account with no studies must behave like a prefix that matches nothing.
@responses.activate
def test_expand_study_id_no_studies_returns_none(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-studies/v1', body=EMPTY_STUDIES_RESPONSE, status=200)
    assert expand_study_id(keyring, '123') is None


# A new account with no studies must give the normal not-found error and not a crash.
@responses.activate
def test_studyid_no_studies_raises_study_id_error(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-studies/v1', body=EMPTY_STUDIES_RESPONSE, status=200)
    with pytest.raises(StudyIDError):
        studyid(keyring, 'Project A')


# A new account with no studies must give the normal not-found error and not a crash.
@responses.activate
def test_studyname_no_studies_raises_study_name_error(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-studies/v1', body=EMPTY_STUDIES_RESPONSE, status=200)
    with pytest.raises(StudyNameError):
        studyname(keyring, '123lrVdb0g6tf3PeJr5ZtZC8')
