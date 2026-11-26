# Controlled demo samples

These files are synthetic training fixtures for the EVIDENCEARCH prototype. They contain no evidence collected from a real computer, user, or device.

- `synthetic_registry_header_only.dat` begins with `regf` so acquisition can demonstrate header recognition and working-copy creation. It is **not a valid Windows Registry hive** and must not be used to make forensic conclusions.
- `synthetic_registry_export.reg` is a tiny, artificial Registry export. The current demo parser does not parse its values; it returns a clearly labelled synthetic record.
- `synthetic_context.txt` illustrates supplementary evidence intake. Its contents are viewable as an original file, but the demo investigator receives only file metadata and does not extract or reason over the text.

In the app, create or select a case, open **Evidence intake**, then click **Create synthetic demo fixture**. The files appear with a DEMO label and SHA-256. Click **Open original** to view supported text/export files, **Parse copy** for Registry fixtures, and then review **Evidence records**, **Evidence graph**, and **AI investigation**. The demo graph has no edges, and claims remain `NOT_ESTABLISHED` without an independent verifier.
