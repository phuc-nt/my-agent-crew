import Foundation
import XCTest
@testable import DesktopHelperCore

final class PreconditionTests: HelperTestCase {
    private struct Guarded {
        let command: String
        let arguments: [String: Any]
        let needsScreen: Bool
        let needsAccessibility: Bool

        var missing: ErrorCode? {
            if needsScreen { return .permissionMissingScreen }
            if needsAccessibility { return .permissionMissingAccessibility }
            return nil
        }
    }

    /// One well-formed request of every command that has preconditions, with the contract's
    /// permission table beside it.
    private let guarded = [
        Guarded(command: "apps", arguments: [:], needsScreen: false, needsAccessibility: false),
        Guarded(command: "windows", arguments: [:], needsScreen: true, needsAccessibility: false),
        Guarded(
            command: "screenshot", arguments: ["max_px": 320],
            needsScreen: true, needsAccessibility: false
        ),
        Guarded(command: "ax", arguments: [:], needsScreen: false, needsAccessibility: true),
        Guarded(
            command: "act", arguments: ["kind": "key", "keys": "enter", "app": "TextEdit"],
            needsScreen: false, needsAccessibility: true
        ),
    ]

    private func send(_ row: Guarded) -> [String: Any] {
        ask(row.command, row.arguments)
    }

    func testEveryGuardedCommandIsDoneOnAReadyMachine() {
        for row in guarded {
            reset()
            assertOK(send(row))
        }
    }

    func testLockedConsoleIsTheAnswerAndNothingElseIsLookedAt() {
        for row in guarded {
            reset()
            system.locked = true
            system.asleep = true
            system.screenRecording = false
            system.accessibility = false
            assertRefused(send(row), .locked, row.command)
            XCTAssertEqual(system.calls, [.isLocked], row.command)
        }
    }

    func testSleepingDisplayIsAnsweredAfterTheLockAndNothingElseIsLookedAt() {
        for row in guarded {
            reset()
            system.asleep = true
            system.screenRecording = false
            system.accessibility = false
            assertRefused(send(row), .displayAsleep, row.command)
            XCTAssertEqual(system.calls, [.isLocked, .isDisplayAsleep], row.command)
        }
    }

    func testLockedBeatsAsleepBeatsMissingPermission() {
        for row in guarded {
            reset()
            system.locked = true
            system.asleep = true
            system.screenRecording = false
            system.accessibility = false
            assertRefused(send(row), .locked, row.command)
            system.locked = false
            assertRefused(send(row), .displayAsleep, row.command)
            system.asleep = false
            if let missing = row.missing {
                assertRefused(send(row), missing, row.command)
                XCTAssertEqual(system.touches, [], row.command)
            }
            system.screenRecording = true
            system.accessibility = true
            assertOK(send(row))
        }
    }

    func testPermissionTableOfTheContract() {
        for row in guarded {
            reset()
            system.screenRecording = false
            system.accessibility = false
            let reply = send(row)
            if row.needsScreen {
                assertRefused(reply, .permissionMissingScreen, row.command)
                XCTAssertEqual(
                    system.calls, [.isLocked, .isDisplayAsleep, .hasScreenRecording], row.command
                )
            } else if row.needsAccessibility {
                assertRefused(reply, .permissionMissingAccessibility, row.command)
                XCTAssertEqual(
                    system.calls, [.isLocked, .isDisplayAsleep, .hasAccessibility], row.command
                )
            } else {
                assertOK(reply)
            }
        }
    }

    func testCommandIsHeldOnlyToThePermissionItNeeds() {
        for row in guarded {
            reset()
            system.screenRecording = false
            let withoutScreen = send(row)
            if row.needsScreen {
                assertRefused(withoutScreen, .permissionMissingScreen, row.command)
            } else {
                assertOK(withoutScreen)
                XCTAssertFalse(system.calls.contains(.hasScreenRecording), row.command)
            }

            reset()
            system.accessibility = false
            let withoutAccessibility = send(row)
            if row.needsAccessibility {
                assertRefused(withoutAccessibility, .permissionMissingAccessibility, row.command)
            } else {
                assertOK(withoutAccessibility)
                XCTAssertFalse(system.calls.contains(.hasAccessibility), row.command)
            }
        }
    }

    func testCommandsOfTheContractsTable() {
        XCTAssertEqual(
            Command.allCases.filter(\.hasPreconditions).map(\.rawValue), guarded.map(\.command)
        )
        for row in guarded {
            let command = Command(rawValue: row.command)
            XCTAssertEqual(command?.needsScreenRecording, row.needsScreen, row.command)
            XCTAssertEqual(command?.needsAccessibility, row.needsAccessibility, row.command)
        }
        for free in [Command.state, Command.requestPermissions] {
            XCTAssertFalse(free.hasPreconditions)
            XCTAssertFalse(free.needsScreenRecording)
            XCTAssertFalse(free.needsAccessibility)
        }
    }

    func testUnknownCommandIsAnsweredWithoutLookingAtTheMachine() {
        system.locked = true
        assertRefused(ask("reboot"), .unknownCommand)
        XCTAssertEqual(system.calls, [])
    }

    func testRequestOfTheWrongShapeIsAnsweredBeforeThePreconditions() {
        system.locked = true
        assertRefused(ask("screenshot", ["max_px": "wide"]), .badRequest)
        assertRefused(ask("screenshot", ["display": "main"]), .badRequest)
        assertRefused(ask("screenshot", ["since": 5]), .badRequest)
        assertRefused(ask("ax", ["app": 5]), .badRequest)
        assertRefused(ask("ax", ["app": ""]), .badRequest)
        assertRefused(ask("ax", ["max_nodes": "many"]), .badRequest)
        XCTAssertEqual(system.calls, [])
    }
}
