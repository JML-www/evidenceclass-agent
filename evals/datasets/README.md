# Stage 11 evaluation datasets

These JSONL fixtures are authorized synthetic records. They contain no private media,
production prompts, model weights, or external credentials. `manifest.v1.json` is the source of
truth for dataset and annotation versions. A record may be assigned to `dev` or `test`, but a
single media asset must never cross splits in a real dataset.

The perception fixture intentionally keeps unknown values (`null`) distinct from a zero count.
The retrieval fixture uses workspace-scoped chunk identifiers. Agent cases include forbidden
tools and terminal states so safety failures cannot be hidden by an average accuracy score.

