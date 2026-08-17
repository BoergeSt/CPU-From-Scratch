// Native (non-cocotb) driver for the Hydrogen interactive session -- see
// `just run-interactive` and hydrogen.core's `interactive` target. Loads an
// assembled program into BRAM and bridges uart0's real serial pins (via the
// virtual RX/TX phys in hydrogen_interactive_tb_top.sv) to a Unix domain
// socket, same architecture the earlier cocotb-based interactive.py used --
// but driven directly, with no Python/VPI in the loop at all.
//
// Why: raw Verilator eval throughput on this design measured ~13M
// cycles/sec with a bare C++ toggle loop, vs. ~390k cycles/sec through
// cocotb (even with the native "gpi" clock and byte-granular
// synchronization) -- cocotb's own VPI/scheduler glue was the dominant
// remaining bottleneck for this specific target. interactive isn't part of
// the verification suite (no assertions, driven entirely by `just
// run-interactive`), so it's the one target where dropping cocotb doesn't
// touch CLAUDE.md's cocotb-as-verification-layer decision; sim/coverage/run
// stay on cocotb.
//
// Config (throttle rate, polling/reporting cadence) is read at startup from
// interactive.conf so it can be tuned without recompiling -- see that file.
//
// Not a directed test -- no assertions, driven by `just run-interactive`.

#include <fcntl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

#include "Vhydrogen_interactive_tb_top.h"
#include "Vhydrogen_interactive_tb_top___024root.h"
#include "verilated.h"

namespace {

using SteadyClock = std::chrono::steady_clock;

struct Config {
    double throttle_cycles_per_sec = 300000.0;
    uint64_t housekeeping_every_cycles = 4096;
    double throughput_report_s = 5.0;
};

std::string Trim(const std::string& s) {
    size_t a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return "";
    size_t b = s.find_last_not_of(" \t\r\n");
    return s.substr(a, b - a + 1);
}

Config LoadConfig(const std::string& path) {
    Config cfg;
    std::ifstream f(path);
    if (!f) {
        fprintf(stderr, "interactive: no config at %s, using defaults\n", path.c_str());
        return cfg;
    }
    std::string line;
    while (std::getline(f, line)) {
        size_t hash = line.find('#');
        if (hash != std::string::npos) line = line.substr(0, hash);
        size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        std::string key = Trim(line.substr(0, eq));
        std::string val = Trim(line.substr(eq + 1));
        if (val.empty()) continue;
        double num = std::strtod(val.c_str(), nullptr);
        if (key == "throttle_cycles_per_sec") {
            cfg.throttle_cycles_per_sec = num;
        } else if (key == "housekeeping_every_cycles") {
            cfg.housekeeping_every_cycles = static_cast<uint64_t>(num);
        } else if (key == "throughput_report_s") {
            cfg.throughput_report_s = num;
        } else {
            fprintf(stderr, "interactive: unknown config key '%s', ignoring\n", key.c_str());
        }
    }
    return cfg;
}

std::vector<uint32_t> LoadProgram(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) {
        fprintf(stderr, "interactive: failed to open program %s\n", path.c_str());
        exit(1);
    }
    std::vector<uint32_t> words;
    uint32_t w;
    while (f.read(reinterpret_cast<char*>(&w), sizeof(w))) {
        words.push_back(w);
    }
    return words;
}

void SetNonBlocking(int fd) {
    int flags = fcntl(fd, F_GETFL, 0);
    fcntl(fd, F_SETFL, flags | O_NONBLOCK);
}

int MakeListener(const std::string& path) {
    unlink(path.c_str());
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) {
        perror("interactive: socket");
        exit(1);
    }
    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    std::strncpy(addr.sun_path, path.c_str(), sizeof(addr.sun_path) - 1);
    if (bind(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        perror("interactive: bind");
        exit(1);
    }
    if (listen(fd, 1) < 0) {
        perror("interactive: listen");
        exit(1);
    }
    SetNonBlocking(fd);
    return fd;
}

char Printable(uint8_t byte) { return (byte >= 32 && byte < 127) ? static_cast<char>(byte) : '.'; }

} // namespace

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);

    const char* program_path = std::getenv("HYDROGEN_PROGRAM");
    if (!program_path) {
        fprintf(stderr, "interactive: HYDROGEN_PROGRAM not set\n");
        return 1;
    }
    const char* socket_env = std::getenv("HYDROGEN_UART0_SOCKET");
    std::string socket_path = socket_env ? socket_env : "/work/dev/uart0.sock";
    const char* config_env = std::getenv("HYDROGEN_INTERACTIVE_CONFIG");
    std::string config_path =
        config_env ? config_env : "/work/machines/hydrogen/rtl/tb/interactive.conf";

    Config cfg = LoadConfig(config_path);
    fprintf(stderr,
            "interactive: throttle_cycles_per_sec=%.0f housekeeping_every_cycles=%llu "
            "throughput_report_s=%.1f\n",
            cfg.throttle_cycles_per_sec,
            static_cast<unsigned long long>(cfg.housekeeping_every_cycles),
            cfg.throughput_report_s);

    VerilatedContext* contextp = new VerilatedContext;
    Vhydrogen_interactive_tb_top* top = new Vhydrogen_interactive_tb_top(contextp);

    std::vector<uint32_t> words = LoadProgram(program_path);
    for (size_t i = 0; i < words.size(); ++i) {
        top->rootp->hydrogen_interactive_tb_top__DOT__core__DOT__bram__DOT__bram[i] = words[i];
    }
    fprintf(stderr, "interactive: loaded %zu words from %s\n", words.size(), program_path);

    top->rst_i = 1;
    top->clk_i = 0;
    top->eval();
    top->clk_i = 1;
    top->eval();
    top->rst_i = 0;

    int listen_fd = MakeListener(socket_path);
    fprintf(stderr, "interactive: listening on %s\n", socket_path.c_str());

    int conn_fd = -1;
    uint8_t prev_rx_valid = 0;

    uint64_t cycles = 0;
    uint64_t cycles_at_last_report = 0;
    SteadyClock::time_point last_report_time = SteadyClock::now();
    SteadyClock::time_point throttle_epoch = SteadyClock::now();
    uint64_t throttle_epoch_cycles = 0;

    for (;;) {
        top->clk_i = 0;
        top->eval();
        top->clk_i = 1;
        top->eval();
        ++cycles;

        // TX: uart0 -> host, decoded by the virtual RX phy. Edge-detected
        // manually since there's no cocotb RisingEdge trigger here.
        if (top->rx_byte_valid_o && !prev_rx_valid) {
            uint8_t byte = top->rx_byte_o;
            if (conn_fd >= 0) {
                if (send(conn_fd, &byte, 1, MSG_NOSIGNAL) <= 0) {
                    close(conn_fd);
                    conn_fd = -1;
                }
            }
            fprintf(stderr, "uart0 TX: 0x%02x '%c'\n", byte, Printable(byte));
        }
        prev_rx_valid = top->rx_byte_valid_o;

        if ((cycles % cfg.housekeeping_every_cycles) != 0) {
            continue;
        }

        if (conn_fd < 0) {
            int fd = accept(listen_fd, nullptr, nullptr);
            if (fd >= 0) {
                SetNonBlocking(fd);
                conn_fd = fd;
                fprintf(stderr, "uart0: client connected\n");
            }
        } else if (!top->tx_fifo_full_o) {
            uint8_t byte;
            ssize_t n = recv(conn_fd, &byte, 1, 0);
            if (n == 1) {
                // RX: host -> uart0, queued into the virtual TX phy's FIFO
                // for RTL-side serialization -- no per-bit timing to drive
                // here, same as the old cocotb harness.
                top->tx_byte_i = byte;
                top->tx_byte_push_i = 1;
                top->clk_i = 0;
                top->eval();
                top->clk_i = 1;
                top->eval();
                ++cycles;
                top->tx_byte_push_i = 0;
                fprintf(stderr, "uart0 RX: 0x%02x '%c'\n", byte, Printable(byte));
            } else if (n == 0) {
                close(conn_fd);
                conn_fd = -1;
                fprintf(stderr, "uart0: client disconnected\n");
            }
            // n < 0: EAGAIN/EWOULDBLOCK -- nothing waiting this round.
        }

        SteadyClock::time_point now = SteadyClock::now();

        if (cfg.throughput_report_s > 0 &&
            std::chrono::duration<double>(now - last_report_time).count() >=
                cfg.throughput_report_s) {
            double dt = std::chrono::duration<double>(now - last_report_time).count();
            uint64_t done = cycles - cycles_at_last_report;
            fprintf(stderr, "throughput: %llu cycles in %.2fs wall (%.0f cycles/sec)\n",
                    static_cast<unsigned long long>(done), dt, done / dt);
            last_report_time = now;
            cycles_at_last_report = cycles;
        }

        // Throttle: pace wall-clock time to cfg.throttle_cycles_per_sec by
        // sleeping off any surplus since throttle_epoch. Runs in bursts of
        // housekeeping_every_cycles cycles rather than smoothly -- the RTL
        // only cares about cycle order, not wall-clock smoothness, so this
        // is fine for a human watching output arrive.
        if (cfg.throttle_cycles_per_sec > 0) {
            uint64_t done = cycles - throttle_epoch_cycles;
            double target_s = done / cfg.throttle_cycles_per_sec;
            double actual_s = std::chrono::duration<double>(now - throttle_epoch).count();
            if (actual_s < target_s) {
                std::this_thread::sleep_for(std::chrono::duration<double>(target_s - actual_s));
            }
            // Resync the epoch periodically so a long slow stretch (e.g. a
            // stalled client) can't build up a debt that later shows as a
            // burst of unthrottled catch-up.
            if (done > 1000000) {
                throttle_epoch = SteadyClock::now();
                throttle_epoch_cycles = cycles;
            }
        }
    }
}
