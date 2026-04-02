// swift-tools-version: 5.7
import PackageDescription

let package = Package(
    name: "WintripRegiekamer",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "WintripRegiekamer", targets: ["WintripRegiekamer"])
    ],
    targets: [
        .executableTarget(
            name: "WintripRegiekamer",
            path: "."
        )
    ]
)
