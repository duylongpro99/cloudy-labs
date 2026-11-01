# Red team: Security Adversary — plan 261031-1358-lab-coverage-hardening

8 findings: 5 High, 3 Medium.

1. High — the generic builder drops the file:// / fileb:// guard, the NAME/DESCRIPTION/TAG_TEXT allowlists and the shorthand protections (validate.py:23-32,133-136; labs/schema.py:47; ops.py:158-161). Needs a mandatory step-0 sanitiser for every string leaf, rejection of list elements that start with `-`, and server-chosen blob paths only.
2. High — registry props will send secrets (Lambda env, CFN Outputs/Parameters) to the LLM. The PROPS allowlist is at chat/prompt.py:55-56,111,136. Needs a `chat_props` allowlist that defaults to empty, plus deny names.
3. High — a runtime TAP_UPSTREAM admin endpoint is either unreachable or reachable from instance containers (api_tap.py:10-12,277-299). Use one tap per emulator with a fixed upstream.
4. High — moto IAM enforcement breaks profile `lab`. The admin principal cloudy-labs-admin is visible and deletable (providers/aws.py:21-26,91-97; aws_profile.py:39-41; runner.py:52-54). Needs credential_process and a registry `protected` filter.
5. High — labaws content leaks into git through hints in lab.yaml (labs/schema.py:144), coverage quotes and tracked plans/*/notes. Put hints in content/hints.yaml, have coverage cite heading/offset only, and add an n-gram check.
6. Medium — a content image endpoint is not designed. Lab slug is not validated (loader.py:56-57). GET routes have only TrustedHost (app.py:160-174). Strip presigned URLs.
7. Medium — /api/reachability has no loop bound, input validation, guard_request or to_thread (app.py:71-87,251-278).
8. Medium — false claims: twin.py does not use PARENT_KINDS (labs/schema.py:9,112). Icons are bundled via import.meta.glob (geometry-cache.ts:11-19). The single region root is enforced (graph/schema.py:82-83). `attribute` gesture (ops.py:21). /api/lab returns more than tasks (app.py:174-199).

Open: does labaws content go into the chat prompt? Hooks must be resolved through a static dict, not importlib.
