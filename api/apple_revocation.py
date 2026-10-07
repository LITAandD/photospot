"""Reauthorize, exchange the short-lived code, then revoke before local deletion.

Refresh tokens are encrypted at rest; transport is injectable for tests.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import urllib.parse
import urllib.request

from fastapi import HTTPException
import jwt
from cryptography.fernet import Fernet
from pydantic import BaseModel, Field

from .providers import ProviderError


class AppleDeletionProof(BaseModel):
    identity_token: str = Field(min_length=1, max_length=16000)
    authorization_code: str = Field(min_length=1, max_length=4096)
    nonce: str = Field(min_length=16, max_length=256)


class DeleteAccountIn(BaseModel):
    apple: AppleDeletionProof | None = None


def post_form(path, fields):
    request = urllib.request.Request('https://appleid.apple.com/auth/' + path,
        data=urllib.parse.urlencode(fields).encode(), headers={'Content-Type':'application/x-www-form-urlencoded'}, method='POST')
    with urllib.request.urlopen(request, timeout=8) as response:
        data = response.read(65537)
    if len(data)>65536: raise ValueError('Invalid Apple response')
    return json.loads(data) if data else {}


class AppleRevoker:
    def __init__(self, settings, verifier, transport=post_form):
        self.settings, self.verifier, self.transport = settings, verifier, transport

    def credentials(self):
        cfg = self.settings
        if not self.verifier or not all((cfg.apple_team_id, cfg.apple_key_id, cfg.apple_private_key_path, cfg.apple_client_id, cfg.apple_token_encryption_key)):
            raise HTTPException(503, 'Apple 계정 삭제 연결이 아직 설정되지 않았어요.')
        now = int(datetime.now(timezone.utc).timestamp())
        secret = jwt.encode({'iss':cfg.apple_team_id, 'iat':now, 'exp':now+300,
                             'aud':'https://appleid.apple.com','sub':cfg.apple_client_id},
                            Path(cfg.apple_private_key_path).read_text(encoding='utf-8'),
                            algorithm='ES256', headers={'kid':cfg.apple_key_id})
        return {'client_id':cfg.apple_client_id,'client_secret':secret}

    def exchange(self, expected_subject, proof):
        cfg = self.settings
        try:
            ident = self.verifier.verify(proof.identity_token, proof.nonce)
        except ProviderError:
            raise HTTPException(401, 'Apple 재인증을 다시 진행해 주세요.')
        if ident.provider_user_id != expected_subject:
            raise HTTPException(403, '연결된 Apple 계정으로 다시 인증해 주세요.')
        # The configured native client must match the signed identity token's aud.
        # This decode only reads claims after the verifier has checked the signature.
        aud = jwt.decode(proof.identity_token, options={'verify_signature':False})['aud']
        if cfg.apple_client_id not in (aud if isinstance(aud,list) else [aud]):
            raise HTTPException(403, 'Apple 앱 식별자가 일치하지 않아요.')
        try:
            common = self.credentials()
            tokens = self.transport('token', {**common,'grant_type':'authorization_code','code':proof.authorization_code})
            exchanged = self.verifier.verify(tokens['id_token'], proof.nonce)
            exchanged_aud = jwt.decode(tokens['id_token'], options={'verify_signature':False})['aud']
            if exchanged.provider_user_id != expected_subject or cfg.apple_client_id not in (exchanged_aud if isinstance(exchanged_aud,list) else [exchanged_aud]):
                raise ValueError('Exchanged identity mismatch')
            token = tokens.get('refresh_token')
            if not token: raise ValueError('Apple token missing')
            return token
        except Exception:
            raise HTTPException(503, 'Apple 인증 연결을 완료하지 못했어요. 다시 시도해 주세요.') from None

    def seal(self, token):
        return Fernet(self.settings.apple_token_encryption_key.encode()).encrypt(token.encode()).decode()

    def revoke(self, expected_subject, proof=None, encrypted_token=None):
        try:
            token = self.exchange(expected_subject, proof) if proof else Fernet(
                self.settings.apple_token_encryption_key.encode()).decrypt(encrypted_token.encode()).decode()
            result = self.transport('revoke', {**self.credentials(),'token':token, 'token_type_hint':'refresh_token'})
            if result.get('error'): raise ValueError('Revocation rejected')
        except Exception:
            # Never return credentials, raw provider errors, or stack traces.
            raise HTTPException(503, 'Apple 연결 해제를 완료하지 못했어요. 계정은 유지되며 다시 시도할 수 있어요.') from None


def revoke_for_account(request, conn, user_id, body):
    with conn.cursor() as cur:
        cur.execute("SELECT provider_user_id FROM auth_identities WHERE user_id=%s AND provider='apple'", (user_id,))
        row = cur.fetchone()
    if not row: return
    with conn.cursor() as cur:
        cur.execute('SELECT encrypted_token FROM apple_grants WHERE user_id=%s', (user_id,))
        grant = cur.fetchone()
    if not grant and (not body or not body.apple):
        raise HTTPException(409, '계정을 삭제하려면 연결된 Apple 계정으로 재인증해 주세요.')
    revoker = getattr(request.app.state, 'apple_revoker', None)
    if not revoker: raise HTTPException(503, 'Apple 계정 삭제 연결을 확인해 주세요.')
    revoker.revoke(row[0], body.apple if body else None, grant[0] if grant else None)


def prepare_grant(request, provider, ident, body):
    if provider != 'apple': return None
    if not body.authorization_code or not body.nonce:
        raise HTTPException(422, 'Apple 승인 코드와 nonce가 필요해요. 최신 앱에서 다시 로그인해 주세요.')
    revoker = request.app.state.apple_revoker
    proof = AppleDeletionProof(identity_token=body.token, authorization_code=body.authorization_code, nonce=body.nonce)
    try:
        return revoker.seal(revoker.exchange(ident.provider_user_id, proof))
    except HTTPException: raise
    except Exception:
        raise HTTPException(503, 'Apple 인증 보관 설정을 확인해 주세요.') from None


def save_grant(conn, user_id, encrypted):
    if encrypted:
        with conn.cursor() as cur:
            cur.execute('''INSERT INTO apple_grants(user_id,encrypted_token) VALUES (%s,%s)
                ON CONFLICT(user_id) DO UPDATE SET encrypted_token=excluded.encrypted_token, updated_at=now()''', (user_id, encrypted))
