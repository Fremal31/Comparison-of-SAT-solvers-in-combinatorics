import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from argparse import Namespace

from main import parse_args, main, DEFAULT_CONFIG_PATH


def _mock_args(config="/fake/config.json", verbose=False):
    return Namespace(config=Path(config), verbose=verbose)


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------

class TestParseArgs:
    def test_default_config_path(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["main.py"])
        result = parse_args()
        assert result.config == DEFAULT_CONFIG_PATH
        assert result.verbose is False

    def test_short_flag(self, monkeypatch, tmp_path: Path):
        cfg = tmp_path / "custom.json"
        monkeypatch.setattr(sys, "argv", ["main.py", "-c", str(cfg)])
        result = parse_args()
        assert result.config == cfg

    def test_long_flag(self, monkeypatch, tmp_path: Path):
        cfg = tmp_path / "custom.json"
        monkeypatch.setattr(sys, "argv", ["main.py", "--config", str(cfg)])
        result = parse_args()
        assert result.config == cfg

    def test_returns_namespace(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["main.py", "-c", "/tmp/test.json"])
        result = parse_args()
        assert isinstance(result.config, Path)

    def test_verbose_flag(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["main.py", "-v"])
        result = parse_args()
        assert result.verbose is True

    def test_unknown_flag_raises(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["main.py", "--unknown"])
        with pytest.raises(SystemExit):
            parse_args()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

class TestMain:
    @patch("main.generate_plots")
    @patch("main.log_results_to_json")
    @patch("main.create_all_writers")
    @patch("main.MultiSolverManager")
    @patch("main.load_config")
    @patch("main.parse_args")
    def test_main_calls_pipeline_in_order(self, mock_args, mock_load, mock_manager_cls,
                                          mock_writers, mock_json, mock_plots):
        mock_args.return_value = _mock_args()
        mock_config = MagicMock()
        mock_config.metrics_measured = {"status": True}
        mock_config.visualization.enabled = False
        mock_load.return_value = mock_config

        mock_manager = MagicMock()
        mock_manager.results = []
        mock_manager_cls.return_value = mock_manager

        mock_close = MagicMock()
        mock_append = MagicMock()
        mock_writers.return_value = (mock_close, mock_append)

        main()

        mock_load.assert_called_once_with(Path("/fake/config.json"))
        mock_manager_cls.assert_called_once_with(config=mock_config)
        mock_manager.run_all_experiments_parallel_separate.assert_called_once()
        mock_close.assert_called_once()
        mock_json.assert_called_once()

    @patch("main.generate_plots")
    @patch("main.log_results_to_json")
    @patch("main.create_all_writers")
    @patch("main.MultiSolverManager")
    @patch("main.load_config")
    @patch("main.parse_args")
    def test_main_generates_plots_when_enabled(self, mock_args, mock_load, mock_manager_cls,
                                                mock_writers, mock_json, mock_plots):
        mock_args.return_value = _mock_args()
        mock_config = MagicMock()
        mock_config.metrics_measured = {}
        mock_config.visualization.enabled = True
        mock_config.visualization.output_dir = "/tmp/plots"
        mock_load.return_value = mock_config

        mock_manager = MagicMock()
        mock_manager.results = []
        mock_manager_cls.return_value = mock_manager

        mock_writers.return_value = (MagicMock(), MagicMock())

        main()

        mock_plots.assert_called_once_with([], "/tmp/plots", timeout=mock_config.timeout)

    @patch("main.generate_plots")
    @patch("main.log_results_to_json")
    @patch("main.create_all_writers")
    @patch("main.MultiSolverManager")
    @patch("main.load_config")
    @patch("main.parse_args")
    def test_main_skips_plots_when_disabled(self, mock_args, mock_load, mock_manager_cls,
                                             mock_writers, mock_json, mock_plots):
        mock_args.return_value = _mock_args()
        mock_config = MagicMock()
        mock_config.metrics_measured = {}
        mock_config.visualization.enabled = False
        mock_load.return_value = mock_config

        mock_manager = MagicMock()
        mock_manager.results = []
        mock_manager_cls.return_value = mock_manager

        mock_writers.return_value = (MagicMock(), MagicMock())

        main()

        mock_plots.assert_not_called()

    @patch("main.GlobalMonitor")
    @patch("main.log_results_to_json")
    @patch("main.create_all_writers")
    @patch("main.MultiSolverManager")
    @patch("main.load_config")
    @patch("main.parse_args")
    def test_main_exits_1_on_experiment_error(self, mock_args, mock_load, mock_manager_cls,
                                               mock_writers, mock_json, mock_monitor):
        mock_args.return_value = _mock_args()
        mock_config = MagicMock()
        mock_config.metrics_measured = {}
        mock_config.visualization.enabled = False
        mock_load.return_value = mock_config

        mock_manager = MagicMock()
        mock_manager.results = []
        mock_manager.run_all_experiments_parallel_separate.side_effect = RuntimeError("boom")
        mock_manager_cls.return_value = mock_manager

        mock_writers.return_value = (MagicMock(), MagicMock())

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("main.GlobalMonitor")
    @patch("main.log_results_to_json")
    @patch("main.create_all_writers")
    @patch("main.MultiSolverManager")
    @patch("main.load_config")
    @patch("main.parse_args")
    def test_main_closes_writers_on_keyboard_interrupt(self, mock_args, mock_load, mock_manager_cls,
                                                        mock_writers, mock_json, mock_monitor):
        mock_args.return_value = _mock_args()
        mock_config = MagicMock()
        mock_config.metrics_measured = {}
        mock_config.visualization.enabled = False
        mock_load.return_value = mock_config

        mock_manager = MagicMock()
        mock_manager.results = []
        mock_manager.run_all_experiments_parallel_separate.side_effect = KeyboardInterrupt
        mock_manager_cls.return_value = mock_manager

        mock_close = MagicMock()
        mock_writers.return_value = (mock_close, MagicMock())

        main()

        mock_close.assert_called_once()
        mock_json.assert_called_once()

    @patch("main.generate_plots")
    @patch("main.log_results_to_json")
    @patch("main.create_all_writers")
    @patch("main.MultiSolverManager")
    @patch("main.load_config")
    @patch("main.parse_args")
    def test_main_passes_timeout_to_plots(self, mock_args, mock_load, mock_manager_cls,
                                           mock_writers, mock_json, mock_plots):
        mock_args.return_value = _mock_args()
        mock_config = MagicMock()
        mock_config.metrics_measured = {}
        mock_config.visualization.enabled = True
        mock_config.visualization.output_dir = "/tmp/plots"
        mock_config.timeout = 3600
        mock_load.return_value = mock_config

        mock_manager = MagicMock()
        mock_manager.results = []
        mock_manager_cls.return_value = mock_manager

        mock_writers.return_value = (MagicMock(), MagicMock())

        main()

        mock_plots.assert_called_once_with([], "/tmp/plots", timeout=3600)
