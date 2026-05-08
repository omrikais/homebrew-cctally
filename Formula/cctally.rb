class Cctally < Formula
  desc "Track Claude Code subscription usage as $-per-1% weekly trend"
  homepage "https://github.com/omrikais/cctally"
  url "https://github.com/omrikais/cctally/archive/refs/tags/v1.2.0.tar.gz"
  sha256 "5d1f7f104471201e6ee89ee586438d6bba5c0a87786772aaff593a2a73582d12"
  license "Apache-2.0"

  depends_on "python@3.13"

  USER_FACING_BINS = %w[
    cctally
    cctally-alerts
    cctally-dashboard
    cctally-dollar-per-percent
    cctally-five-hour-blocks
    cctally-five-hour-breakdown
    cctally-forecast
    cctally-project
    cctally-refresh-usage
    cctally-release
    cctally-sync-week
    cctally-tui
  ].freeze

  def install
    USER_FACING_BINS.each { |name| (libexec/"bin").install "bin/#{name}" }
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
