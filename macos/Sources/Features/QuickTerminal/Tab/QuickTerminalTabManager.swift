import GhosttyKit
import SwiftUI

/// Custom TabManager for the "quick" terminal
class QuickTerminalTabManager: ObservableObject {

    /// All currently open tabs
    @Published private(set) var tabs: [QuickTerminalTab] = []

    /// The current tab in focus
    @Published private(set) var currentTab: QuickTerminalTab? {
        didSet {
            if let oldTab = oldValue, let oldSurfaceTree = controller?.surfaceTree {
                oldTab.surfaceTree = oldSurfaceTree
                oldTab.updateFocusedSurfaceIfOwned(controller?.focusedSurface)
            }

            controller?.activeQuickTerminalTab = currentTab
            guard let currentTab else { return }

            self.controller?.surfaceTree = currentTab.surfaceTree

            DispatchQueue.main.async {
                // Find the focused surface, or fallback to the first surface (for new tabs)
                let surfaceToFocus = currentTab.focusedSurface

                if let surface = surfaceToFocus {
                    self.controller?.focusSurface(surface)
                    self.controller?.syncFocusToSurfaceTree()
                }

                // This is the only way I found to force a re-render, and it's still not perfect.
                // I'm getting some artifacts  when switching tabs, characters not rendering correctly,
                // stuff like that.
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                    guard let surfaceTree = self.controller?.surfaceTree else { return }

                    for surface in surfaceTree {
                        surface.sizeDidChange(surface.bounds.size)
                    }
                }
            }
        }
    }

    /// The tab currently being renamed via the title prompt sheet. When set,
    /// `QuickTerminalController.titleOverride` and `applyTitleToWindow` target
    /// this tab instead of `currentTab`, allowing the user to rename an
    /// inactive tab without changing the selection. Cleared by the controller
    /// when the sheet ends (`windowDidEndSheet`).
    weak var tabBeingRenamed: QuickTerminalTab? {
        didSet { controller?.applyTitleToWindow() }
    }

    /// Reference to the "quick" terminal Controller
    private(set) weak var controller: QuickTerminalController?

    var currentTabIndex: Int? {
        tabs.firstIndex { $0.id == currentTab?.id }
    }

    /// Access to the Ghostty config for keybinding lookups
    var config: Ghostty.Config? {
        controller?.ghostty.config
    }

    /// Forwards to the controller's undo manager (the app-level expiring manager).
    /// Returns nil before the controller has a window so callers can short-circuit.
    private var undoManager: ExpiringUndoManager? {
        controller?.undoManager
    }

    private var undoExpiration: Duration {
        controller?.undoExpiration ?? .seconds(60)
    }

    init(controller: QuickTerminalController, restorationState: QuickTerminalRestorableState? = nil) {
        self.controller = controller

        // Check if restoration is enabled
        let shouldRestore = controller.ghostty.config.windowSaveState != "never"

        if shouldRestore,
           let savedState = restorationState,
           !savedState.tabs.isEmpty {
            // Restore tabs from saved state
            for state in savedState.tabs {
                let tab = QuickTerminalTab(
                    surfaceTree: state.surfaceTree,
                    title: state.title,
                    focusedSurfaceID: state.focusedSurface
                )
                tab.titleOverride = state.titleOverride
                tab.tabColor = state.tabColor
                tabs.append(tab)
            }

            // Select the previously current tab
            if tabs.indices.contains(savedState.currentTabIndex) {
                selectTab(tabs[savedState.currentTabIndex])
            } else if let first = tabs.first {
                selectTab(first)
            }
        }
    }

    /// Restores tabs from saved state. This replaces any existing tabs.
    /// - Parameters:
    ///   - tabStates: The saved tab states to restore
    ///   - currentIndex: The index of the tab that should be selected
    func restoreTabs(from tabStates: [QuickTerminalTabState<Ghostty.SurfaceView>], currentIndex: Int) {
        // Clear existing tabs without triggering close logic
        tabs.removeAll()
        currentTab = nil

        // Restore each tab from state
        for state in tabStates {
            let tab = QuickTerminalTab(
                surfaceTree: state.surfaceTree,
                title: state.title,
                focusedSurfaceID: state.focusedSurface
            )
            tab.titleOverride = state.titleOverride
            tab.tabColor = state.tabColor
            tabs.append(tab)
        }

        // Select the previously current tab
        if tabs.indices.contains(currentIndex) {
            selectTab(tabs[currentIndex])
        } else if let first = tabs.first {
            selectTab(first)
        }
    }

    // MARK: Methods

    func addNewTab(baseConfig: Ghostty.SurfaceConfiguration? = nil) {
        performAddNewTab(baseConfig: baseConfig, registerUndo: true)
    }

    @discardableResult
    private func performAddNewTab(
        baseConfig: Ghostty.SurfaceConfiguration?,
        registerUndo: Bool
    ) -> QuickTerminalTab? {
        guard let ghostty = controller?.ghostty, let app = ghostty.app else { return nil }

        let config = Self.quickTerminalConfiguration(inheriting: baseConfig)
        let leaf: Ghostty.SurfaceView = .init(app, baseConfig: config)
        let surfaceTree: SplitTree<Ghostty.SurfaceView> = .init(view: leaf)
        let tabIndex = tabs.count + 1
        let newTab = QuickTerminalTab(surfaceTree: surfaceTree, title: "Terminal \(tabIndex)")

        let insertIndex = (currentTabIndex.map { $0 + 1 }) ?? tabs.count
        insertTab(newTab, at: insertIndex, undoActionName: registerUndo ? "New Tab" : nil)
        return newTab
    }

    /// Adds an existing surface tree as a new tab in the quick terminal.
    /// Used when moving a tab from a regular terminal window to the quick terminal.
    func addTabWithSurfaceTree(
        _ surfaceTree: SplitTree<Ghostty.SurfaceView>,
        title: String? = nil,
        titleOverride: String? = nil,
        tabColor: TerminalTabColor = .none,
        focusedSurfaceID: String? = nil
    ) {
        let tabIndex = tabs.count + 1
        let newTab = QuickTerminalTab(
            surfaceTree: surfaceTree,
            title: title ?? "Terminal \(tabIndex)",
            focusedSurfaceID: focusedSurfaceID
        )
        newTab.titleOverride = titleOverride
        newTab.tabColor = tabColor
        let insertIndex = (currentTabIndex.map { $0 + 1 }) ?? tabs.count
        // Moving a native tab here currently destroys its old AppKit window.
        // Registering a plain insertion undo would remove the quick-terminal
        // tab without recreating that window, so do not advertise a lossy undo.
        insertTab(newTab, at: insertIndex, undoActionName: nil)
    }

    func selectTab(_ tab: QuickTerminalTab) {
        guard currentTab?.id != tab.id else { return }

        currentTab = tab
    }

    func closeTab(_ tab: QuickTerminalTab, withConfirmation: Bool = true) {
        guard tabs.contains(where: { $0.id == tab.id }) else { return }
        let close = { [weak self] in
            self?.removeTab(tab, undoActionName: "Close Tab")
        }
        guard withConfirmation, let controller else {
            close()
            return
        }
        controller.confirmCloseIfNeeded(of: [tab.surfaceTree], action: close)
    }

    func closeAllTabs(except: QuickTerminalTab) {
        let toClose = self.tabs.filter { $0.id != except.id }
        guard !toClose.isEmpty else { return }

        closeTabs(toClose, actionName: "Close Other Tabs")
    }

    func closeTabsToTheRight(of tab: QuickTerminalTab) {
        guard let index = tabs.firstIndex(where: { $0.id == tab.id }) else { return }
        let toClose = tabs.enumerated().filter { $0.offset > index }.map { $0.element }
        guard !toClose.isEmpty else { return }

        closeTabs(toClose, actionName: "Close Tabs to the Right")
    }

    private func closeTabs(_ tabsToClose: [QuickTerminalTab], actionName: String) {
        let close = { [weak self] in
            guard let self else { return }
            self.undoManager?.beginUndoGrouping()
            self.undoManager?.setActionName(actionName)
            defer { self.undoManager?.endUndoGrouping() }

            for tab in tabsToClose {
                self.removeTab(tab, undoActionName: actionName)
            }
        }

        guard let controller else {
            close()
            return
        }
        controller.confirmCloseIfNeeded(of: tabsToClose.map(\.surfaceTree), action: close)
    }

    func moveTab(from source: IndexSet, to destination: Int) {
        // Capture pre-move order so we can register an undo.
        let preMoveOrder = tabs
        tabs.move(fromOffsets: source, toOffset: destination)
        guard tabs.map(\.id) != preMoveOrder.map(\.id) else { return }
        registerReorderUndo(to: preMoveOrder, actionName: "Move Tab")
    }

    // MARK: Undoable Helpers

    /// Inserts a tab at the given index and (optionally) registers an undo that
    /// closes it again. The undo closure re-registers a redo via `removeTab`.
    private func insertTab(_ tab: QuickTerminalTab, at index: Int, undoActionName: String?) {
        let clamped = max(0, min(index, tabs.count))
        tabs.insert(tab, at: clamped)
        selectTab(tab)

        guard let undoActionName, let undoManager else { return }
        undoManager.setActionName(undoActionName)
        undoManager.registerUndo(withTarget: self, expiresAfter: undoExpiration) { target in
            target.removeTab(tab, undoActionName: undoActionName)
        }
    }

    /// Removes a tab without closing its surfaces (the tab object itself
    /// retains them, so undo can restore it). Registers an undo that re-inserts.
    ///
    /// When the removal empties the tab list, also clears the controller's
    /// surface tree and animates the quick terminal out. This runs here (rather
    /// than only in `closeTab`) so it fires consistently on every removal path,
    /// including the redo of an undone insert.
    private func removeTab(_ tab: QuickTerminalTab, undoActionName: String?) {
        guard let index = tabs.firstIndex(where: { $0.id == tab.id }) else { return }
        let previousSelection = currentTab

        tabs.remove(at: index)

        if currentTab?.id == tab.id {
            if tabs.isEmpty {
                currentTab = nil
            } else {
                let newIndex = min(index, tabs.count - 1)
                selectTab(tabs[newIndex])
            }
        }

        // Empty-tabs cleanup. Order matters: this runs *after* the
        // currentTab → nil transition above so the dying tab has already
        // captured the live surface tree in its `currentTab.didSet`.
        if tabs.isEmpty {
            controller?.surfaceTree = .init()
            controller?.animateOut()
        }

        guard let undoActionName, let undoManager else { return }
        undoManager.setActionName(undoActionName)
        undoManager.registerUndo(withTarget: self, expiresAfter: undoExpiration) { target in
            let wasEmpty = target.tabs.isEmpty
            target.insertTab(tab, at: index, undoActionName: undoActionName)
            if let previousSelection, target.tabs.contains(where: { $0.id == previousSelection.id }) {
                target.selectTab(previousSelection)
            }
            if wasEmpty {
                target.controller?.animateIn()
            }
        }
    }

    /// Restores a previous tab ordering and registers a redo that re-applies
    /// the current ordering.
    private func registerReorderUndo(to previousOrder: [QuickTerminalTab], actionName: String) {
        guard let undoManager else { return }
        let newOrder = tabs
        undoManager.setActionName(actionName)
        undoManager.registerUndo(withTarget: self, expiresAfter: undoExpiration) { target in
            target.tabs = previousOrder
            target.registerReorderUndo(to: newOrder, actionName: actionName)
        }
    }

    func selectNextTab() {
        guard !tabs.isEmpty, let currentTabIndex else { return }

        let nextIndex = (currentTabIndex + 1) % tabs.count
        selectTab(tabs[nextIndex])
    }

    func selectPreviousTab() {
        guard !tabs.isEmpty, let currentTabIndex else { return }

        let previousIndex = (currentTabIndex - 1 + tabs.count) % tabs.count
        selectTab(tabs[previousIndex])
    }

    /// Moves a tab to a new regular terminal window at the specified screen location.
    /// The tab's surface tree is transferred to the new window.
    func moveTabToNewWindow(_ tab: QuickTerminalTab, at screenLocation: NSPoint? = nil) {
        guard let ghostty = controller?.ghostty else { return }
        guard controller?.window != nil else { return }

        // If this is the current tab, sync its surface tree from the controller
        if currentTab?.id == tab.id, let controllerTree = controller?.surfaceTree {
            tab.surfaceTree = controllerTree
            tab.updateFocusedSurfaceIfOwned(controller?.focusedSurface)
        }

        // Capture the target location (use provided location or current mouse position)
        let targetLocation = screenLocation ?? NSEvent.mouseLocation

        // Create a new TerminalController with the existing surface tree
        let newController = TerminalController(
            ghostty,
            withSurfaceTree: tab.surfaceTree
        )

        // Transfer tab title and color to the new controller/window
        newController.titleOverride = tab.titleOverride

        // Show the new window first (this triggers window loading)
        newController.showWindow(nil)

        // Position the window after showing. We need to do this in async to ensure
        // any window cascading or layout passes have completed first.
        if let newWindow = newController.window {
            // Transfer tab color to the new window
            (newWindow as? TerminalWindow)?.tabColor = tab.tabColor

            let windowSize = newWindow.frame.size
            // Position so the top center of the title bar is at the drop point
            let newOrigin = NSPoint(
                x: targetLocation.x - windowSize.width / 2,
                y: targetLocation.y - windowSize.height
            )
            // Use async to ensure positioning happens after any pending layout
            DispatchQueue.main.async {
                newWindow.setFrameOrigin(newOrigin)
                newWindow.makeKeyAndOrderFront(nil)
            }
        }

        NSApp.activate(ignoringOtherApps: true)

        // Remove the tab from the quick terminal without closing its surfaces
        // (they're now owned by the new window)
        removeTabWithoutClosingSurfaces(tab)
        restoreFocus(of: tab, in: newController)

    }

    /// Removes a tab from the tab list without closing its surfaces.
    /// Used when transferring a tab to a new window.
    func removeTabWithoutClosingSurfaces(_ tab: QuickTerminalTab) {
        guard let index = tabs.firstIndex(where: { $0.id == tab.id }) else { return }

        tabs.remove(at: index)

        if currentTab?.id == tab.id {
            if tabs.isEmpty {
                currentTab = nil
                controller?.surfaceTree = .init()
                controller?.animateOut()
            } else {
                let newIndex = min(index, tabs.count - 1)
                selectTab(tabs[newIndex])
            }
        }
    }

    // MARK: - Notifications

    /// BaseTerminalController only owns the selected tab's surface tree. Handle
    /// process exits and close actions for retained background tab trees here.
    @objc func onCloseSurface(_ notification: Notification) {
        guard let target = notification.object as? Ghostty.SurfaceView else { return }
        guard let tab = tabs.first(where: {
            $0.id != currentTab?.id && $0.surfaceTree.contains(target)
        }) else { return }

        let close = { [weak self, weak tab] in
            guard let self, let tab else { return }
            guard self.tabs.contains(where: { $0.id == tab.id }) else { return }

            // The tab may have become current while a confirmation sheet was
            // open. In that case the controller tree is authoritative and its
            // normal split/tab close path must own the mutation.
            if self.currentTab?.id == tab.id, let controller = self.controller {
                controller.closeSurface(target, withConfirmation: false)
                return
            }

            guard let result = Self.inactiveSurfaceCloseResult(
                target: target,
                tree: tab.surfaceTree,
                focused: tab.focusedSurface
            ) else { return }

            guard let newTree = result.tree else {
                self.removeTab(tab, undoActionName: "Close Tab")
                return
            }

            tab.surfaceTree = newTree
            tab.updateFocusedSurface(result.focused)
        }

        let processAlive = (notification.userInfo?["process_alive"] as? Bool) ?? false
        guard processAlive, let controller else {
            close()
            return
        }
        controller.confirmClose(
            messageText: "Close Terminal?",
            informativeText: "The terminal still has a running process. If you close the terminal the process will be killed.",
            completion: close
        )
    }

    @objc func onMoveTab(_ notification: Notification) {
        guard let target = notification.object as? Ghostty.SurfaceView else { return }
        guard target == controller?.focusedSurface else { return }

        guard
            let action = notification.userInfo?[Notification.Name.GhosttyMoveTabKey] as? Ghostty.Action.MoveTab
        else { return }

        guard action.amount != 0 else { return }

        guard let currentTabIndex else { return }

        // Determine the final index we want to insert our tab
        let finalIndex: Int
        if action.amount < 0 {
            finalIndex = max(0, currentTabIndex - min(currentTabIndex, -action.amount))
        } else {
            let remaining: Int = tabs.count - 1 - currentTabIndex
            finalIndex = currentTabIndex + min(remaining, action.amount)
        }

        if finalIndex != currentTabIndex {
            let destination = Self.collectionMoveDestination(
                from: currentTabIndex,
                to: finalIndex
            )
            moveTab(from: IndexSet(integer: currentTabIndex), to: destination)
        }
    }

    @objc func onGoToTab(_ notification: Notification) {
        // Only respond to goto_tab when the quick terminal window is focused
        guard controller?.window?.isKeyWindow == true else { return }
        guard let target = notification.object as? Ghostty.SurfaceView else { return }
        guard target == controller?.focusedSurface else { return }
        guard !tabs.isEmpty else { return }

        guard let tabEnumAny = notification.userInfo?[Ghostty.Notification.GotoTabKey] else { return }
        guard let tabEnum = tabEnumAny as? ghostty_action_goto_tab_e else { return }

        let tabIndex: Int32 = tabEnum.rawValue

        if tabIndex == GHOSTTY_GOTO_TAB_PREVIOUS.rawValue {
            selectPreviousTab()
        } else if tabIndex == GHOSTTY_GOTO_TAB_NEXT.rawValue {
            selectNextTab()
        } else if tabIndex == GHOSTTY_GOTO_TAB_LAST.rawValue {
            selectTab(tabs[tabs.count - 1])
        } else if tabIndex > 0 {
            // Numeric tab index (1-indexed)
            guard let arrayIndex = Self.numericTabIndex(tabIndex, tabCount: tabs.count) else { return }
            selectTab(tabs[arrayIndex])
        }
    }

    /// Translate a desired final index into `Array.move`'s pre-removal offset.
    static func collectionMoveDestination(from source: Int, to finalIndex: Int) -> Int {
        finalIndex > source ? finalIndex + 1 : finalIndex
    }

    /// Resolve a 1-indexed goto-tab action, clamping oversized shortcuts to
    /// the last tab to match regular macOS terminal windows.
    static func numericTabIndex(_ requested: Int32, tabCount: Int) -> Int? {
        guard requested > 0, tabCount > 0 else { return nil }
        return min(Int(requested - 1), tabCount - 1)
    }

    /// Computes the retained-tree update for a background surface close. A nil
    /// tree means the only surface was closed and the containing tab should go.
    static func inactiveSurfaceCloseResult<ViewType>(
        target: ViewType,
        tree: SplitTree<ViewType>,
        focused: ViewType?
    ) -> (tree: SplitTree<ViewType>?, focused: ViewType?)?
    where ViewType: NSView & Codable & Identifiable {
        guard let node = tree.root?.node(view: target) else { return nil }
        guard tree.isSplit else { return (nil, nil) }

        let replacementFocus: ViewType?
        if focused === target, let root = tree.root {
            let direction: SplitTree<ViewType>.FocusDirection = root.leftmostLeaf() === node.leftmostLeaf()
                ? .next
                : .previous
            replacementFocus = tree.focusTarget(for: direction, from: node)
        } else {
            replacementFocus = focused
        }

        return (tree.removing(node), replacementFocus)
    }

    private func restoreFocus(of tab: QuickTerminalTab, in controller: TerminalController) {
        guard let surface = tab.focusedSurface else { return }
        controller.focusedSurfaceDidChange(to: surface)
        controller.syncSurfaceTreeOcclusionState()
        controller.focusSurface(surface)
    }

    /// Every surface in the dedicated panel must retain the quick-terminal
    /// marker while preserving inherited cwd, command, font, and environment.
    static func quickTerminalConfiguration(
        inheriting baseConfig: Ghostty.SurfaceConfiguration?
    ) -> Ghostty.SurfaceConfiguration {
        var config = baseConfig ?? Ghostty.SurfaceConfiguration()
        config.environmentVariables["GHOSTTY_QUICK_TERMINAL"] = "1"
        return config
    }
}
