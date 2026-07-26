# User onboarding runbook

1. Create the user in Authentik.
2. Require password reset or enrolment.
3. Enrol MFA when required.
4. Add the user to `ai-users`.
5. Confirm Authentik application binding.
6. Have the user sign in to Open WebUI once.
7. Assign Open WebUI groups and model access.
8. Create or verify private knowledge permissions.
9. Test that shared knowledge is readable.
10. Test that administrator features are unavailable.
11. Test STT: have the user record a voice message and confirm the transcription appears in the chat input.
12. Test TTS: confirm the user can play back a spoken response.
