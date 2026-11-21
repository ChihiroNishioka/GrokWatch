# Expose only the reply endpoint to your tailnet

The Gateway listens on `127.0.0.1:8767`. Tailscale Serve terminates HTTPS for tailnet clients and proxies only `/v1/reply` to that local listener. The URL shape is `https://<mac-mini>.<tailnet>.ts.net/v1/reply`.

The current [Tailscale Serve CLI reference](https://tailscale.com/docs/reference/tailscale-cli/serve) supports HTTPS reverse proxies to `http://127.0.0.1` and path mounts. Serve is tailnet-only. Funnel exposes services to the public internet and is not used here.

## Check existing Serve configuration

Before adding the route, inspect the current configuration. Continue only if no unrelated Serve route needs to remain unchanged.

```bash
tailscale serve status --json
tailscale funnel status --json
```

The Serve output must not contain unrelated routes. The Funnel output must contain no active public service.

## Add the reply route

After the owner approves installation, start the Gateway and confirm that `status.sh` reports a healthy listener. Then add this path mount.

```bash
tailscale serve --bg --https=443 --set-path=/v1/reply http://127.0.0.1:8767
tailscale serve status --json
```

Confirm that the Serve status lists only `/v1/reply` for this Gateway. From another tailnet device, request `https://<mac-mini>.<tailnet>.ts.net/v1/reply`. A `405` response to GET confirms that the request reached the POST-only route. Send a signed POST to verify a full reply.

The `--bg` setting keeps Serve active after a reboot. Tailscale provisions the HTTPS certificate for the tailnet name.

## Remove the reply route

Turn off only the path mount added above.

```bash
tailscale serve --https=443 --set-path=/v1/reply off
tailscale serve status --json
tailscale funnel status --json
```

Confirm that the reply route is absent and Funnel still has no active service. Do not use `tailscale serve reset`, because it removes every Serve configuration on the device.
