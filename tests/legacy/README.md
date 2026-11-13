# Legacy audit tests (superseded, do not expect them to pass)

`test_mvp_api.py` is the original audit suite from before integration. It
asserts the OLD behaviour: unsalted SHA-256 passwords, no token, client-supplied
`farmer_id`, and no `/api/orders` endpoint.

Integration deliberately changed all of that (bcrypt, JWT, `farmer_id` derived
from the token, real orders), so 3 of its 6 tests now fail on purpose. It is
kept here only as a record of what the pre-integration API looked like.

The current suite is `../test_integration.py`: 8 passed, 0 failed.
