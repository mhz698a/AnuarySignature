# Structure branch synchronization and local credential application

## Working with a branch or Pull Request

The Structure synchronization dialog works against the branch currently checked out in the local clone.

1. Open **Ajustes → Sincronizar Structure con GitHub**.
2. Use **Actualizar ramas** to fetch the branches exposed by `origin`.
3. Select the branch to work on in **Rama de trabajo**.
4. The application checks the local checkout against `origin/<selected-branch>`.
5. **Descargar cambios** performs a backup and a fast-forward merge from that branch.
6. **Subir cambios** commits local Structure changes and pushes to that same branch.

A Pull Request is reviewed from its source branch. To work on a Pull Request hosted in this repository, select its head/source branch. For example, Structure PR #2 uses `phase-6/reviewed-character-colours`; select that branch rather than `main`.

The selector lists branches fetched from the configured `origin`. Pull Requests whose source branch exists only in a different fork are not selectable through this dialog yet.

Branch changes are refused while the checkout has modified or untracked files. The application does not use stash, reset, checkout-overwrite or force-push. Downloads remain fast-forward-only. Diverged local and remote histories must be resolved before the application can upload or download.

Only the selected branch is pushed to. The application never redirects a push from a feature branch or Pull Request source branch to `main`.

## Applying cached character changes to this computer

The private Structure file `__structure__/characters_cache.json` stores character metadata, while each individual `__*.json` credential remains in the character's folder on the configured dependent drive.

After downloading or switching to a branch with a different character cache, the application preserves a copy of that cache outside the Git checkout:

`%LOCALAPPDATA%\\AnuarySignature\\CharacterCacheSync\\pending_characters_cache.json`

This snapshot is captured before the application rescans the dependent drive. The scan can therefore rebuild its runtime cache without losing the remote values that still need review.

The comparison is available in **Herramientas → Aplicar cambios de caché a credenciales locales**. It matches the character using year, name and alterego and searches the local dependent drive for the actual credential. It does not trust an absolute `character_json_path` from another computer.

The dialog displays field-level differences between Structure and the local `character_data`. Each field can be selected independently. Non-empty Structure values are selected by default; empty values are not selected automatically. Invalid or ambiguous character matches remain visible as errors and cannot be applied.

When applying selected values:

- The service rechecks that the cache and local credential still match the preview.
- It creates a full pre-change copy of each credential under `%LOCALAPPDATA%\\AnuarySignature\\CharacterCacheSync\\Backups\\<batch-id>\\`.
- It updates only selected allowlisted credential fields and writes each JSON atomically.
- It does not replace or delete image files.
- It records the local application history in AppData. It does not create a shared Structure order result, so each computer can independently apply the same cache update to its own credentials.

Image references must resolve to existing local image files inside the matching character folder. A path pointing to another computer is not copied or applied. To transfer an image, use the reviewed `replace_character_asset` Structure order, which copies an image from `orders/assets/` and preserves the existing local image.

A pending snapshot is retained if some differences remain, a record cannot be matched, or a local credential changed after preview. The application blocks another branch switch, download or backup restore until the pending snapshot is applied or explicitly discarded. This prevents a later branch change from overwriting an unreviewed cache snapshot.

**Descartar snapshot pendiente** removes only the AppData review copy. It does not modify dependent-drive credentials, images, or repository files. A fresh snapshot can then be captured from the current Structure cache.

## Safety boundaries

- The cache application is a reviewed metadata update, not a bulk overwrite.
- Only the existing credential allowlist can be changed.
- Character identity must resolve uniquely on the configured drive.
- Existing local edits made after preview are not overwritten.
- The previous credential bytes remain recoverable from the batch backup.
- No delete, move, rename, shell, script or arbitrary-code operation is introduced.
