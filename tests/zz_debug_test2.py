import pytest
from tests.test_demo_runner import (
    test_demo_runner_walks_a_package_to_completed_when_every_competency_is_demonstrated as orig
)

def test_debug2(db_session, sample_program, sample_package, capsys):
    orig(db_session, sample_program, sample_package)
