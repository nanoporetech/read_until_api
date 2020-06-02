import logging
import time
from multiprocessing.pool import ThreadPool
import typing


def run_workflow(
    client: "read_until.ReadUntilClient",
    analysis_worker: typing.Callable[[], None],
    n_workers: int,
    run_time: float,
    runner_kwargs: typing.Optional[typing.Dict] = None,
):
    """Run an analysis function against a ReadUntilClient.

    :param client: `ReadUntilClient` instance.
    :param analysis worker: a function to process reads. It should exit in
        response to `client.is_running == False`.
    :param n_workers: number of incarnations of `analysis_worker` to run.
    :param run_time: time (in seconds) to run workflow.
    :param runner_kwargs: keyword arguments for `client.run()`.

    :returns: a list of results, on item per worker.

    """
    logger = logging.getLogger("Manager")

    if not runner_kwargs:
        runner_kwargs = {}

    results = []
    pool = ThreadPool(n_workers)
    logger.info("Creating %s workers", n_workers)
    try:
        # start the client
        client.run(**runner_kwargs)

        # start a pool of workers
        for _ in range(n_workers):
            results.append(pool.apply_async(analysis_worker))
        pool.close()

        # wait a bit before closing down
        time.sleep(run_time)
        logger.info("Sending reset")
        client.reset()
        pool.join()
    except KeyboardInterrupt:
        logger.info("Caught ctrl-c, terminating workflow.")
        client.reset()

    # collect results (if any)
    collected = []
    for result in results:
        try:
            res = result.get(timeout=3)
        except TimeoutError:
            logger.warning("Worker function did not exit successfully.")
            collected.append(None)
        except Exception:  # pylint: disable=broad-except
            logger.exception("Worker raise exception:")
        else:
            logger.info("Worker exited successfully.")
            collected.append(res)
    pool.terminate()
    return collected
