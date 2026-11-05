#!/bin/sh
# Render assigns a different port to every instance and passes it as $PORT at runtime.
# That value cannot be read in a Dockerfile CMD/HEALTHCHECK: Docker expands ${VAR} while
# building (so it bakes in the build-time default), and writing $$PORT to defer it turns
# into the shell's own PID. Resolving it here, in a file the parser does not substitute,
# is the only form that survives both.
#
# One worker is deliberate: the engines read the AOI from process-global src.config and
# every survey writes the same fixed filenames under outputs/, so extra workers would each
# hold their own config and site lock while overwriting each other's deliverables. Raise
# it only once an immutable per-job SiteContext with a namespaced output dir replaces them.
exec uvicorn src.api:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
