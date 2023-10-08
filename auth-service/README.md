# Auth Service

In Monolithic applications, a user provides username and password, the security module validates user credentials and create a session for the user.
A session Id is returned to the client and the client stores the session Id in cookies and send it with each request as an identifier for the user.

This approach making the service statefull has an impact on the scalability because a session should be stored for each user, the more users you’ll have the more memory you’ll need.
Also if you divide the app into multiple services, you’ll need to find a way to share the session between services.

In the token based authentication, authentication service generates the token and send it to the client but it doesn’t store it.
The client has to send the token with every request in the Authorization header.
This token holds the user’s identity information.

In this project we’ll use JWT (JSON Web Token) to implement token based authentication.

## JWT

A JWT token would look like below

```
eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJhZGFtIiwiYXV0aG9yaXRpZXMiOlsiVVNFUiJdLCJpYXQiOjE1OTE2NDQ2NjMsImV4cCI6MTU5MTczMTA2M30.9pR6sK-kJmG6Zm7aWVqNrQy9MZ8ponYKz3Wc3nfKU7MD4oXkifjAEgkB6Uc-Dswp3yjWIiNLrpMd7S9SZ1_D_A
```

If you notice there are 3 sections in the token separated by dot “.”, these sections are Header.Payload.Signature

1. Header: contains metadata like type of the token and the hashing algorithm that is used in Signature section.

```
{
"typ": "JWT",
"alg": "HS512"
}
```

2. Payload: contains the claims, claims are statements about an entity (typically, the user) and additional data.

```
{
  "sub": "adam",
  "authorities": [
    "USER"
  ],
  "iat": 1591644663,
  "exp": 1591731063
}
```

3. Signature: contains the signature of the token creator, to make sure that the token isn’t changed.

```
HMACSHA512(
  base64UrlEncode(header) + "." +
  base64UrlEncode(payload),
  Secret
)
```

## Auth Service responsibilities

1. Registering new users.

2. Validating user credentials and issue a token.

3. Stores and retrieves users profile.

4. Manages users.

5. Sends a message whenever a user created/updated.
