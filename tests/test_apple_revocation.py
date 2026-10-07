import hashlib
import time
from types import SimpleNamespace
import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import HTTPException
from api.apple_revocation import AppleRevoker, AppleDeletionProof, revoke_for_account
from api.config import Settings
from api.providers import AppleVerifier, ProviderError

@pytest.fixture
def apple(tmp_path):
    rsa_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    private=ec.generate_private_key(ec.SECP256R1())
    path=tmp_path/'test.p8'
    path.write_bytes(private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    cfg=Settings(apple_audiences=['app.photospot'],apple_client_id='app.photospot',apple_team_id='team',apple_key_id='key',
                 apple_private_key_path=str(path),apple_token_encryption_key=Fernet.generate_key().decode())
    nonce='nonce-for-test-1234'
    def token(sub='apple-user',omit_exp=False,**patch):
        claims={'iss':'https://appleid.apple.com','aud':cfg.apple_client_id,'sub':sub,'iat':int(time.time()),
                'exp':int(time.time())+600,'nonce':hashlib.sha256(nonce.encode()).hexdigest(),**patch}
        if omit_exp: del claims['exp']
        return jwt.encode(claims,rsa_key,algorithm='RS256')
    verifier=AppleVerifier(cfg.apple_audiences,SimpleNamespace(get_signing_key_from_jwt=lambda _:SimpleNamespace(key=rsa_key.public_key())))
    calls=[]
    def transport(endpoint,fields):
        secret=jwt.decode(fields['client_secret'],private.public_key(),algorithms=['ES256'],audience='https://appleid.apple.com')
        assert secret['sub']==cfg.apple_client_id and secret['iss']=='team'
        calls.append((endpoint,fields))
        return {'id_token':token(),'refresh_token':'secret-refresh'} if endpoint=='token' else {}
    return AppleRevoker(cfg,verifier,transport),AppleDeletionProof(identity_token=token(),authorization_code='one-time-code',nonce=nonce),calls,token

def test_exchange_encrypt_and_revoke_without_device_reauthentication(apple):
    revoker,proof,calls,_=apple
    sealed=revoker.seal(revoker.exchange('apple-user',proof))
    assert 'secret-refresh' not in sealed
    revoker.revoke('apple-user',encrypted_token=sealed)
    assert [c[0] for c in calls]==['token','revoke']
    assert calls[-1][1]['token']=='secret-refresh' and calls[-1][1]['token_type_hint']=='refresh_token'

def test_legacy_reauthentication_rejects_wrong_account_and_invalid_nonce(apple):
    revoker,proof,calls,token=apple
    with pytest.raises(HTTPException): revoker.revoke('someone-else',proof)
    assert calls==[]
    proof.identity_token=token(nonce='wrong')
    with pytest.raises(HTTPException): revoker.revoke('apple-user',proof)
    assert calls==[]

def test_expired_or_missing_expiry_tokens_are_rejected(apple):
    revoker,proof,_,token=apple
    with pytest.raises(ProviderError): revoker.verifier.verify(token(exp=int(time.time())-1),proof.nonce)
    with pytest.raises(ProviderError): revoker.verifier.verify(token(omit_exp=True),proof.nonce)

def test_failure_does_not_perform_local_deletion(apple):
    revoker,proof,_,_=apple
    sealed=revoker.seal('secret-refresh')
    def fail(*_): raise TimeoutError('secret-refresh should never leak')
    revoker.transport=fail
    class Conn:
        def cursor(self): return self
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self,sql,args):
            assert sql.startswith('SELECT')  # No user data mutation on provider failure.
            self.row=('apple-user',) if 'auth_identities' in sql else (sealed,)
        def fetchone(self): return self.row
    request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(apple_revoker=revoker)))
    with pytest.raises(HTTPException) as failure: revoke_for_account(request,Conn(),'user',None)
    assert failure.value.status_code==503 and 'secret-refresh' not in failure.value.detail

def test_exchange_response_for_another_account_never_revokes(apple):
    revoker,proof,calls,token=apple
    def bad(endpoint,fields):
        calls.append(endpoint)
        return {'id_token':token('other'),'refresh_token':'other-refresh'}
    revoker.transport=bad
    with pytest.raises(HTTPException): revoker.revoke('apple-user',proof)
    assert calls==['token']
