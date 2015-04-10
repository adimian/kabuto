def test_login(client):
    # not yet logged in
    rv = client.get('/')
    assert rv.status_code == 401

    # logging in
    rv = client.post('/login', data={'login': 'me',
                                     'password': 'Secret'})
    assert rv.status_code == 200

    # logged in, yay
    rv = client.get('/')
    assert rv.status_code == 200


def test_empty_login(client):
    # not yet logged in
    rv = client.get('/')
    assert rv.status_code == 401

    # logging in
    rv = client.post('/login', data={})
    assert rv.status_code == 401
