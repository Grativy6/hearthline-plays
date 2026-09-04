# Attestation sidecars

Receipts are immutable events. A later human signature, RFC 3161 timestamp,
transparency-log proof, review, or correction is a new sidecar keyed to the
receipt's content-addressed event ID. It is never inserted into or used to
rewrite the original receipt.

An attestation must identify its scheme, signer or witness evidence, target
event ID, creation time and evidence basis. A key identifies a key; binding it
to a person requires separate identity evidence.

No human cryptographic signature or trusted timestamp exists at genesis.
