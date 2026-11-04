package fx.service;

public class Drawer {
    private Shape shape;

    public void paint() {
        shape.draw();                                  // refused: 6 implementations > K = 5
        Notifier n = new Notifier() {                  // L0 anon_impl
            public void send(String m) { }
        };
        n.send("x");
    }
}
