# Repository workflow

- After requested app changes, increment the patch version in `app/package.json`
  and `app/package-lock.json`, and keep the README version current.
- Run the relevant tests and production build. Push to GitHub `main` when the
  user requests publishing the changes; preserve newer remote commits.
- Do not install or update the user's local app, invoke its updater, replace
  `/Applications/Atlas.app`, or restart the installed app. The user updates it
  manually. Repository builds and isolated tests are allowed.
