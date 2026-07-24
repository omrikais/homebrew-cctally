class Cctally < Formula
  desc "Track Claude Code subscription usage as $-per-1% weekly trend"
  homepage "https://github.com/omrikais/cctally"
  url "https://github.com/omrikais/cctally/archive/refs/tags/v1.82.0.tar.gz"
  sha256 "1d89b8f4b1a0c55e77dcc6a3b2cc3bccc3fa5df11e98b767fb2c906f0f10ba0c"
  license "Apache-2.0"

  depends_on "python@3.13"

  USER_FACING_BINS = %w[
    cctally
    cctally-alerts
    cctally-budget
    cctally-dashboard
    cctally-dollar-per-percent
    cctally-five-hour-blocks
    cctally-five-hour-breakdown
    cctally-forecast
    cctally-project
    cctally-refresh-usage
    cctally-statusline
    cctally-sync-week
    cctally-transcript
    cctally-tui
    cctally-update
  ].freeze

  # Runtime siblings late-loaded by bin/cctally via _load_sibling
  # (Path(__file__).parent / "<name>.py"). Globbed so future
  # _lib_*.py / _cctally_*.py additions land automatically — parity
  # guard lives in tests/test_package_files.py. NOT symlinked into
  # `bin/` (import-only; should not appear on the user's PATH).
  RUNTIME_SIBLING_GLOBS = %w[bin/_lib_*.py bin/_cctally_*.py].freeze

  def install
    USER_FACING_BINS.each { |name| (libexec/"bin").install "bin/#{name}" }
    Dir.glob(RUNTIME_SIBLING_GLOBS).each { |path| (libexec/"bin").install path }
    (libexec/"dashboard").install "dashboard/static"
    libexec.install "CHANGELOG.md"

    inreplace libexec/"bin/cctally", %r{^#!.*$},
      "#!#{Formula["python@3.13"].opt_bin}/python3.13"

    USER_FACING_BINS.each { |name| bin.install_symlink libexec/"bin/#{name}" }
  end

  def caveats
    <<~EOS
      To finish setup, run:
        cctally setup

      This installs additive Claude Code hooks (~/.claude/settings.json)
      and bootstraps the local SQLite cache (~/.local/share/cctally/).

      Details: https://github.com/omrikais/cctally#installation
    EOS
  end

  test do
    output = shell_output("#{bin}/cctally --help")
    assert_match "cctally", output
    assert_match "report", output
  end
end
