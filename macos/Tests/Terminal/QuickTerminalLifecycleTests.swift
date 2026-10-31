import AppKit
import Testing
@testable import Ghostty

/// Exercise the real tab manager and base controller together: switching the
/// selected split tree must not end ownership of retained sessions.
@Suite(.serialized)
@MainActor
struct QuickTerminalLifecycleTests {
    /// Controllers schedule focus/animation work and undo retains closed tabs.
    /// Their surfaces must never outlive the embedded app that owns them.
    /// Match the real app's process lifetime instead of freeing it per test.
    @MainActor
    private final class Fixture {
        let config: TemporaryConfig
        let ghostty: Ghostty.App

        init() throws {
            config = try TemporaryConfig("""
            initial-window = false
            window-save-state = never
            command = /usr/bin/true
            wait-after-command = true
            keybind = clear
            """)
            ghostty = Ghostty.App(configPath: config.temporaryFile.path())
        }
    }

    private static let fixture: Result<Fixture, Error> = Result { try Fixture() }

    private func withTerminal(
        _ body: (QuickTerminalController, Ghostty.SurfaceView, Ghostty.SurfaceView) throws -> Void
    ) throws {
        let ghostty = try Self.fixture.get().ghostty
        let app = try #require(ghostty.app)
        let controller = QuickTerminalController(ghostty)
        let first = Ghostty.SurfaceView(app)
        let second = Ghostty.SurfaceView(app)
        controller.tabManager.addTabWithSurfaceTree(.init(view: first))
        controller.tabManager.addTabWithSurfaceTree(.init(view: second))
        defer {
            for tab in controller.tabManager.tabs {
                controller.tabManager.closeTab(tab, withConfirmation: false)
            }
            controller.window?.close()
        }
        try body(controller, first, second)
    }

    @Test func switchingTabsPreservesOwnershipAndPendingClipboardRequest() throws {
        try withTerminal { controller, first, second in
            let tabs = controller.tabManager.tabs
            controller.tabManager.selectTab(tabs[0])
            let request = Ghostty.ClipboardConfirmationRequest(
                surface: first, contents: "pending", kind: .osc_52_read
            ) { _, _, _ in }
            first.pendingClipboardConfirmation = request

            controller.tabManager.selectTab(tabs[1])
            #expect(controller.surfaceTree.contains(second))
            #expect(!controller.surfaceTree.contains(first))
            #expect(BaseTerminalController.controller(owning: first) === controller)
            #expect(first.pendingClipboardConfirmation === request)

            controller.tabManager.selectTab(tabs[0])
            #expect(first.pendingClipboardConfirmation === request)
            #expect(controller.ownedSurfaces.count == 2)
        }
    }

    @Test func closingBackgroundTabReleasesOwnershipAndCancelsClipboardRequest() throws {
        try withTerminal { controller, first, second in
            first.pendingClipboardConfirmation = Ghostty.ClipboardConfirmationRequest(
                surface: first, contents: "pending", kind: .osc_52_read
            ) { _, _, _ in }
            controller.tabManager.closeTab(controller.tabManager.tabs[0], withConfirmation: false)
            #expect(first.pendingClipboardConfirmation == nil)
            #expect(BaseTerminalController.controller(owning: first) == nil)
            #expect(BaseTerminalController.controller(owning: second) === controller)
            #expect(controller.ownedSurfaces.count == 1)
        }
    }

    @Test func backgroundProcessExitRemovesOnlyItsOwnTab() throws {
        try withTerminal { controller, first, second in
            controller.tabManager.onCloseSurface(Notification(
                name: Ghostty.Notification.ghosttyCloseSurface,
                object: first,
                userInfo: ["process_alive": false]
            ))
            #expect(controller.tabManager.tabs.count == 1)
            #expect(controller.surfaceTree.contains(second))
            #expect(BaseTerminalController.controller(owning: first) == nil)
        }
    }

    @Test func transferringOwnershipPreservesPendingClipboardRequest() throws {
        try withTerminal { controller, first, _ in
            let request = Ghostty.ClipboardConfirmationRequest(
                surface: first, contents: "pending", kind: .osc_52_read
            ) { _, _, _ in }
            first.pendingClipboardConfirmation = request
            let destination = TerminalController(controller.ghostty, withSurfaceTree: .init(view: first))
            controller.tabManager.removeTabWithoutClosingSurfaces(controller.tabManager.tabs[0])
            #expect(BaseTerminalController.controller(owning: first) === destination)
            #expect(first.pendingClipboardConfirmation === request)
            destination.surfaceTree = .init()
            #expect(first.pendingClipboardConfirmation == nil)
        }
    }
}
