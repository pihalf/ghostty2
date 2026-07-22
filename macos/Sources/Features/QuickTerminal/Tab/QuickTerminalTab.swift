import Combine
import SwiftUI

class QuickTerminalTab: ObservableObject, Identifiable {

    /// User-defined title override. When set, this takes precedence over the surface title.
    @Published var titleOverride: String?

    /// The latest title from the focused surface (without any override applied).
    @Published private(set) var surfaceTitle: String

    /// Whether the focused surface currently has its bell flag set. The view layer
    /// decides whether to prefix the title with a bell glyph based on the user's
    /// `bell-features` config — this property just reflects raw surface state.
    @Published private(set) var surfaceBell: Bool = false

    /// The tab color for visual identification
    @Published var tabColor: TerminalTabColor = .none

    /// The current background color of the focused surface (dynamic if set,
    /// otherwise the configured background color).
    @Published private(set) var backgroundColor: Color?

    /// The configured background opacity of the focused surface. Used to keep
    /// the active tab visually continuous with the translucent terminal below it.
    @Published private(set) var backgroundOpacity: Double = 1

    let id = UUID()
    var surfaceTree: SplitTree<Ghostty.SurfaceView>

    /// The surface that was focused when this tab was last active. Focus state
    /// isn't encoded by `SurfaceView`, so we persist the identifier with the tab.
    private(set) var focusedSurfaceID: String?

    /// The displayed title for the tab. Override wins, otherwise the surface title.
    /// Bell prefix is applied at the view layer where the config is available.
    var title: String { titleOverride ?? surfaceTitle }

    private var cancellables: Set<AnyCancellable> = []

    init(
        surfaceTree: SplitTree<Ghostty.SurfaceView>,
        title: String = "Terminal",
        focusedSurfaceID: String? = nil
    ) {
        self.surfaceTree = surfaceTree
        let focusedSurface = focusedSurfaceID.flatMap { id in
            surfaceTree.first { $0.id.uuidString == id }
        } ?? surfaceTree.first { $0.focused } ?? surfaceTree.first
        self.focusedSurfaceID = focusedSurface?.id.uuidString
        self.surfaceTitle = focusedSurface?.title ?? title

        subscribeToSurface(focusedSurface)
    }

    /// Updates the surface subscriptions to track the given surface.
    /// Called when the focused surface changes within this tab.
    func updateFocusedSurface(_ surface: Ghostty.SurfaceView?) {
        focusedSurfaceID = surface?.id.uuidString
        subscribeToSurface(surface)
    }

    /// Updates focus only when the candidate belongs to this tab. Focus changes
    /// are delivered asynchronously, so a rapid tab switch can briefly leave the
    /// controller pointing at a surface from the previously selected tab.
    func updateFocusedSurfaceIfOwned(_ surface: Ghostty.SurfaceView?) {
        guard let surface, surfaceTree.contains(surface) else { return }
        updateFocusedSurface(surface)
    }

    /// Resolve the saved focused surface against the current tree.
    var focusedSurface: Ghostty.SurfaceView? {
        focusedSurfaceID.flatMap { id in
            surfaceTree.first { $0.id.uuidString == id }
        } ?? surfaceTree.first
    }

    private func subscribeToSurface(_ surface: Ghostty.SurfaceView?) {
        cancellables.removeAll()
        guard let surface else {
            backgroundColor = nil
            backgroundOpacity = 1
            surfaceBell = false
            return
        }

        // Mirrors BaseTerminalController's focused-surface title pipeline so the
        // tab's `surfaceTitle` and `surfaceBell` stay in sync from a single sink.
        surface.$title
            .combineLatest(surface.$bell)
            .receive(on: DispatchQueue.main)
            .sink { [weak self] title, bell in
                guard let self else { return }
                self.surfaceTitle = title
                self.surfaceBell = bell
            }
            .store(in: &cancellables)

        // Prefer the dynamic background color (OSC 11, etc.) and fall back to the
        // surface's configured background. Opacity always comes from the config.
        surface.$backgroundColor
            .combineLatest(surface.$derivedConfig)
            .receive(on: DispatchQueue.main)
            .sink { [weak self] dynamic, config in
                guard let self else { return }
                self.backgroundColor = dynamic ?? config.backgroundColor
                self.backgroundOpacity = config.backgroundOpacity
            }
            .store(in: &cancellables)
    }
}
