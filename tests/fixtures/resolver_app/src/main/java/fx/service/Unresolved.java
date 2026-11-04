package fx.service;

import com.unknown.Lib;

public class Unresolved {
    private Lib lib;

    public void run() {
        lib.go();                                      // refused: unresolved
    }
}
