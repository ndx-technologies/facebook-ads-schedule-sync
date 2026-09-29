Enable/Disable Facebook Ads on schedule.

```bash
FB_APP_ID=... FB_APP_SECRET=... FB_ACCESS_TOKEN=... python3 main.py --spec spec.json --apply
```

Credentials come from the environment, or from the file named by `<NAME>_FILE`:

- `FB_APP_ID`
- `FB_APP_SECRET`
- `FB_ACCESS_TOKEN`

```json
{
	"timezone": "America/Sao_Paulo",
	"ad_account_id": "...",
	"campaigns": [
		{
			"id": "...",
			"windows": [
				{"weekday": "fri", "from": "05:00", "until": "23:00"},
				{"weekday": "sat", "from": "05:00", "until": "23:00"},
				{"weekday": "sun", "from": "05:00", "until": "23:00"}
			]
		}
	]
}
```

Spec fields, defaults and window semantics: `spec.schema.json`.
