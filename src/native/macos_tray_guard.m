// Guard Qt's status-item callbacks on macOS 27 until the upstream fix ships.
// Only QStatusItemDelegate is affected; AppKit/NSEvent methods are untouched.
// Upstream: qtbase/src/plugins/platforms/cocoa/qcocoasystemtrayicon.mm
#import <AppKit/AppKit.h>
#import <objc/runtime.h>

typedef void (*ClickCallback)(id, SEL);
typedef void (*MenuCallback)(id, SEL, NSNotification *);
static ClickCallback originalClick;
static MenuCallback originalMenu;
static BOOL installed = NO;

static BOOL currentEventIsMouse(void)
{
    NSEvent *event = NSApp.currentEvent;
    if (!event)
        return NO;
    switch (event.type) {
    case NSEventTypeLeftMouseDown:
    case NSEventTypeLeftMouseUp:
    case NSEventTypeRightMouseDown:
    case NSEventTypeRightMouseUp:
    case NSEventTypeOtherMouseDown:
    case NSEventTypeOtherMouseUp:
    case NSEventTypeMouseMoved:
    case NSEventTypeLeftMouseDragged:
    case NSEventTypeRightMouseDragged:
    case NSEventTypeOtherMouseDragged:
        return YES;
    default:
        return NO;
    }
}

static void guardedClick(id self, SEL selector)
{
    if (currentEventIsMouse())
        originalClick(self, selector);
}

static void guardedMenu(id self, SEL selector, NSNotification *notification)
{
    // The native menu is already opening. Skip only Qt's unused activated
    // signal for non-mouse events, not menu tracking or menu item actions.
    if (currentEventIsMouse())
        originalMenu(self, selector, notification);
}

// Called once, on the GUI thread after QApplication loaded the Cocoa plugin.
int noah_install_macos_tray_guard(void)
{
    if (installed)
        return 1;
    Class delegate = objc_getClass("QStatusItemDelegate");
    if (!delegate)
        return 0;
    SEL click = sel_registerName("statusItemClicked");
    SEL menu = sel_registerName("statusItemMenuBeganTracking:");
    Method clickMethod = class_getInstanceMethod(delegate, click);
    Method menuMethod = class_getInstanceMethod(delegate, menu);
    if (!clickMethod || !menuMethod)
        return 0;
    originalClick = (ClickCallback)method_getImplementation(clickMethod);
    originalMenu = (MenuCallback)method_getImplementation(menuMethod);
    class_replaceMethod(delegate, click, (IMP)guardedClick, method_getTypeEncoding(clickMethod));
    class_replaceMethod(delegate, menu, (IMP)guardedMenu, method_getTypeEncoding(menuMethod));
    installed = YES;
    return 1;
}
