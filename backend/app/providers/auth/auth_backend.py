from http.client import HTTPConnection

from starlette.authentication import AuthCredentials, AuthenticationBackend, AuthenticationError

from app.auth.service import verify_user

# based on starlette.authentication.AuthenticationBackend


class AuthBackend(AuthenticationBackend):
    async def authenticate(self, conn: HTTPConnection):
        if "Authorization" not in conn.headers:
            return

        # get token from headers
        auth = conn.headers["Authorization"]

        try:
            scheme, encoded_jwt = auth.split()
        except ValueError:
            # HTTP 400 (defined in middleware) as opposed to 401
            # also does not set application type json
            raise AuthenticationError({"detail": "Invalid credentials"})

        if scheme.lower() != "bearer":
            return

        current_user = await verify_user(encoded_jwt)
        if current_user is None:
            raise AuthenticationError({"detail": "Invalid credentials"})

        return AuthCredentials(), current_user
