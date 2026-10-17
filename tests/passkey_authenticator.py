"""
Software FIDO2 authenticator for tests: produces real WebAuthn registration and assertion
payloads (P-256 ES256, "none" attestation) that py_webauthn verifies cryptographically.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

FLAG_USER_PRESENT = 0x01
FLAG_USER_VERIFIED = 0x04
FLAG_ATTESTED_DATA = 0x40


class SoftAuthenticator:
    def __init__(self, origin: str = "http://localhost:3000", rp_id: str = "localhost") -> None:
        self.origin = origin
        self.rp_id = rp_id
        self.credential_id = os.urandom(32)
        self._key = ec.generate_private_key(ec.SECP256R1())
        self.sign_count = 0

    def _client_data(self, ceremony: str, challenge_b64: str) -> bytes:
        return json.dumps(
            {"type": ceremony, "challenge": challenge_b64, "origin": self.origin, "crossOrigin": False}
        ).encode()

    def _cose_public_key(self) -> bytes:
        numbers = self._key.public_key().public_numbers()
        return cbor2.dumps(
            {1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big")}
        )

    def create(self, options: dict, flags: int = FLAG_USER_PRESENT | FLAG_USER_VERIFIED) -> dict:
        client_data = self._client_data("webauthn.create", options["challenge"])
        auth_data = (
            hashlib.sha256(self.rp_id.encode()).digest()
            + bytes([flags | FLAG_ATTESTED_DATA])
            + struct.pack(">I", self.sign_count)
            + bytes(16)
            + struct.pack(">H", len(self.credential_id))
            + self.credential_id
            + self._cose_public_key()
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": bytes_to_base64url(self.credential_id),
            "rawId": bytes_to_base64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "attestationObject": bytes_to_base64url(attestation),
            },
        }

    def get(self, options: dict, flags: int = FLAG_USER_PRESENT | FLAG_USER_VERIFIED) -> dict:
        allowed = [base64url_to_bytes(c["id"]) for c in options.get("allowCredentials", [])]
        assert not allowed or self.credential_id in allowed, "credential not in allowCredentials"
        self.sign_count += 1
        client_data = self._client_data("webauthn.get", options["challenge"])
        auth_data = (
            hashlib.sha256(self.rp_id.encode()).digest()
            + bytes([flags])
            + struct.pack(">I", self.sign_count)
        )
        signature = self._key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            "id": bytes_to_base64url(self.credential_id),
            "rawId": bytes_to_base64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(signature),
            },
        }


def execute_with_passkey(client, intent_id: str):
    """Runs the full API passkey ceremony (register, challenge, sign, execute) for one intent."""
    from services.security.passkeys import passkey_registry

    tenant_id = client.get(f"/api/v1/actions/{intent_id}").json()["tenant_id"]
    passkey_registry.clear()
    authenticator = SoftAuthenticator()

    reg_options = client.post("/api/v1/actions/passkeys/register/options", json={"tenant_id": tenant_id})
    assert reg_options.status_code == 200, reg_options.text
    registered = client.post(
        "/api/v1/actions/passkeys/register",
        json={"tenant_id": tenant_id, "credential": authenticator.create(reg_options.json())},
    )
    assert registered.status_code == 201, registered.text

    auth_options = client.post(f"/api/v1/actions/{intent_id}/passkey-options")
    assert auth_options.status_code == 200, auth_options.text
    return client.post(
        f"/api/v1/actions/{intent_id}/execute",
        json={"webauthn_assertion": authenticator.get(auth_options.json())},
    )
