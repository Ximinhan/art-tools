import click
from artcommonlib import redis

from pyartcd import jenkins, util
from pyartcd.cli import cli, click_coroutine, pass_runtime
from pyartcd.locks import Lock, LockManager
from pyartcd.runtime import Runtime


async def run_for(group: str, runtime: Runtime, lock_manager: LockManager) -> str:
    """
    Run scan for a single group.
    Returns a status string: 'SUCCESS', 'FAILURE', 'UNSTABLE', 'SKIPPED', or 'ERROR'.
    """
    # Skip if locked on layered products scan
    scan_lock_name = Lock.LAYERED_PRODUCTS_SCAN.value.format(group=group)
    if await lock_manager.is_locked(scan_lock_name):
        runtime.logger.info(f'[{group}] Locked on {scan_lock_name}, skipping')
        return 'SKIPPED'

    # Skip if locked on layered products build
    build_lock_name = Lock.LAYERED_PRODUCTS_BUILD.value.format(group=group)
    if await lock_manager.is_locked(build_lock_name):
        runtime.logger.info(f'[{group}] Locked on {build_lock_name}, skipping')
        return 'SKIPPED'

    # Skip if frozen
    if not await util.is_build_permitted(
        group=group, doozer_working=str(runtime.working_dir / "doozer_working-" / group)
    ):
        runtime.logger.info('[%s] Not permitted by freeze_automation, skipping', group)
        return 'SKIPPED'

    # Schedule layered products scan and wait for completion
    runtime.logger.info('[%s] Scheduling layered-products-scan-konflux', group)

    try:
        result = jenkins.start_layered_products_scan_konflux(
            group=group, block_until_building=True, block_until_complete=True
        )
        runtime.logger.info('[%s] Build completed with result: %s', group, result)
        return result or 'SUCCESS'
    except Exception as e:
        runtime.logger.error('[%s] Build failed with error: %s', group, e)
        return 'ERROR'


@cli.command('schedule-layered-products-scan')
@click.option('--group', '-g', required=True, help='Layered products group to scan', multiple=True)
@pass_runtime
@click_coroutine
async def layered_products_scan(runtime: Runtime, group: tuple):
    jenkins.init_jenkins()
    lock_manager = LockManager([redis.redis_url()])
    results = {}
    try:
        for g in group:
            runtime.logger.info('--- Starting scan for group: %s ---', g)
            results[g] = await run_for(g, runtime, lock_manager)
            runtime.logger.info('--- Finished scan for group: %s --- Result: %s', g, results[g])
    finally:
        await lock_manager.destroy()

    # Summarize overall status
    runtime.logger.info('=== Layered Products Scan Summary ===')
    for g, result in results.items():
        runtime.logger.info('  %-30s %s', g, result)

    failed = [g for g, r in results.items() if r in ('FAILURE', 'ERROR', 'UNSTABLE')]
    skipped = [g for g, r in results.items() if r == 'SKIPPED']
    succeeded = [g for g, r in results.items() if r == 'SUCCESS']

    runtime.logger.info('Succeeded: %d, Failed: %d, Skipped: %d', len(succeeded), len(failed), len(skipped))

    if failed:
        runtime.logger.error('Failed groups: %s', ', '.join(failed))
        raise RuntimeError(f'Layered products scan failed for: {", ".join(failed)}')
