# Digital commerce implementation plan

Spec: ../specs/2026-11-01-all-design.md. Execution: native, continuous; the user explicitly authorized implementation, main push and merged-branch cleanup.

1. Import pinned MIT monitor and AGPL seller sources, preserve notices; configure two services and a seller startup gate. README v0.1.0 records import and prior design commit.
2. TDD SQLite catalog/listing/execution storage, authenticated commerce API and seller HTTP adapter. Preview is local, isolated and never calls the seller; live writes require explicit mode and account. Unknown publish outcomes retain mapping. Tests use real SQLite and an HTTP boundary fixture.
3. Build unified Vue commerce pages for catalog, publish, accounts, replies, stock, orders and relist; reuse existing Vue components/fetch conventions. Rebuild generated assets normally. README v0.2.0 records core integration.
4. Verify offline digital delivery, duplicate events, depleted stock, interrupted send and conditional relist, plus live adapter schemas. Preserve existing monitor safety patches. README v0.3.0 records closure and tests.
5. Run relevant upstream and new regression tests, frontend typecheck/build, start the app and check UI. Fresh whole-branch review; fix material findings. Record limits, especially unavailable Docker/real-account validation. README final version notes; merge main, push, verify remote SHA, delete only merged task branches.

Review focus: preview never restores real listeners; authentication is server-side; unknown writes never blind-retry; platform product IDs stay separate from source IDs; only one engine owns fulfillment.
