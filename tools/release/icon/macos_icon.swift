// Deterministic macOS-only derivative of the approved PNG master.
// SwiftUI supplies Apple's continuous-corner geometry; CoreGraphics/ImageIO
// rasterize it without pip packages or a second checked-in bitmap master.
import AppKit
import SwiftUI
import ImageIO

func writePNG(_ image: CGImage, to path: String) throws {
    guard let destination = CGImageDestinationCreateWithURL(URL(fileURLWithPath: path) as CFURL,
        "public.png" as CFString, 1, nil) else { throw NSError(domain: "icon", code: 1) }
    CGImageDestinationAddImage(destination, image, nil)
    guard CGImageDestinationFinalize(destination) else { throw NSError(domain: "icon", code: 2) }
}

guard CommandLine.arguments.count == 3 else {
    fputs("Usage: macos_icon.swift approved-master.png macos-icon.png\n", stderr)
    exit(2)
}
let sourceURL = URL(fileURLWithPath: CommandLine.arguments[1])
guard let source = CGImageSourceCreateWithURL(sourceURL as CFURL, nil),
      let artwork = CGImageSourceCreateImageAtIndex(source, 0, nil),
      artwork.width == 1024, artwork.height == 1024,
      let context = CGContext(data: nil, width: 1024, height: 1024,
          bitsPerComponent: 8, bytesPerRow: 1024 * 4,
          space: CGColorSpace(name: CGColorSpace.sRGB)!,
          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
    fputs("Expected a readable 1024x1024 approved master\n", stderr)
    exit(1)
}
let body = CGRect(x: 100, y: 100, width: 824, height: 824)
let shape = RoundedRectangle(cornerRadius: 185, style: .continuous).path(in: body).cgPath
context.setAllowsAntialiasing(true)
context.setShouldAntialias(true)
context.setFillColor(CGColor(gray: 0, alpha: 1))
context.setShadow(offset: CGSize(width: 0, height: -8), blur: 16,
                  color: CGColor(gray: 0, alpha: 0.24))
context.addPath(shape)
context.fillPath()
context.setShadow(offset: .zero, blur: 0, color: nil)
context.addPath(shape)
context.clip()
context.interpolationQuality = .high
context.draw(artwork, in: body)
guard let result = context.makeImage() else { exit(1) }
try writePNG(result, to: CommandLine.arguments[2])
