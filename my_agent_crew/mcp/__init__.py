"""A client for MCP servers: tools that live on another machine, reached over streamable
HTTP and handed to the agents whose profile names the server. `config` reads what
`config.yaml` says of them, `wire` and `session` talk to one, `oauth` signs in, `tools`
turns what a server lists into tools of the crew, and `hub` holds it all for a runtime."""
