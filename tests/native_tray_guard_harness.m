// Exercise the Objective-C callback boundary without creating windows or
// calling clickCount on a real invalid NSEvent (which would crash macOS).
#import <AppKit/AppKit.h>

extern int noah_install_macos_tray_guard(void);
static int clicks, menus, invalidReads;

@interface TestEvent : NSObject
@property NSEventType type;
- (NSInteger)clickCount;
@end
@implementation TestEvent
- (NSInteger)clickCount {
    if (self.type == NSEventTypeSystemDefined || self.type == NSEventTypeKeyDown)
        invalidReads++;
    return 1;
}
@end

@interface TestApplication : NSObject
@property(strong) TestEvent *currentEvent;
@end
@implementation TestApplication
@end

@interface QStatusItemDelegate : NSObject
- (void)statusItemClicked;
- (void)statusItemMenuBeganTracking:(NSNotification *)notification;
@end
@implementation QStatusItemDelegate
- (void)statusItemClicked { [NSApp.currentEvent clickCount]; clicks++; }
- (void)statusItemMenuBeganTracking:(NSNotification *)notification {
    [NSApp.currentEvent clickCount]; menus++;
}
@end

int main(void) {
    @autoreleasepool {
        TestApplication *application = [TestApplication new];
        NSApp = (NSApplication *)application;
        QStatusItemDelegate *delegate = [QStatusItemDelegate new];
        if (!noah_install_macos_tray_guard() || !noah_install_macos_tray_guard())
            return 1;
        // Keyboard/system/nil events must not reach the original Qt callback.
        [delegate statusItemClicked];
        [delegate statusItemMenuBeganTracking:nil];
        TestEvent *event = [TestEvent new];
        application.currentEvent = event;
        event.type = NSEventTypeSystemDefined;
        [delegate statusItemClicked];
        [delegate statusItemMenuBeganTracking:nil];
        event.type = NSEventTypeKeyDown;
        [delegate statusItemClicked];
        [delegate statusItemMenuBeganTracking:nil];
        if (clicks || menus || invalidReads)
            return 2;
        // Mouse callbacks must still delegate normally.
        event.type = NSEventTypeLeftMouseDown;
        [delegate statusItemClicked];
        [delegate statusItemMenuBeganTracking:nil];
        event.type = NSEventTypeRightMouseDown;
        [delegate statusItemClicked];
        [delegate statusItemMenuBeganTracking:nil];
        if (clicks != 2 || menus != 2 || invalidReads)
            return 3;
        NSApp = nil;
        puts("Native tray guard: system/keyboard/nil blocked, mouse callbacks preserved");
    }
    return 0;
}
