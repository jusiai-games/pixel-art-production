using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEditor.U2D.Sprites;
using UnityEngine;

namespace PixelArtProduction.Editor
{
    internal sealed class PixelArtImporter : AssetPostprocessor
    {
        private const string ManagedFolder = "Assets/Art/PixelArt/";

        [Serializable]
        private sealed class Sheet
        {
            public int version;
            public string kind;
            public int width;
            public int height;
            public int cell;
            public int ppu;
            public float pivotX;
            public float pivotY;
            public string sha256;
            public Cell[] sprites;
        }

        [Serializable]
        private sealed class Cell
        {
            public string name;
            public int x;
            public int y;
        }

        private static bool IsManagedPng(string path) =>
            path.StartsWith(ManagedFolder, StringComparison.Ordinal) &&
            path.EndsWith(".png", StringComparison.OrdinalIgnoreCase);

        public override uint GetVersion() => 2;

        private void OnPreprocessTexture()
        {
            if (!IsManagedPng(assetPath))
                return;

            var sidecar = Path.ChangeExtension(assetPath, ".sprite.json");
            context?.DependsOnSourceAsset(sidecar);
            try
            {
                var sheet = JsonUtility.FromJson<Sheet>(File.ReadAllText(sidecar));
                ValidateSheet(sheet);
                var importer = (TextureImporter)assetImporter;
                ConfigureTexture(importer, sheet.ppu);
                SetSlices(importer, sheet);
            }
            catch (Exception error) when (error is IOException || error is InvalidDataException || error is ArgumentException)
            {
                var message = $"{assetPath}: {error.Message} Rebuild and import the matching PNG and .sprite.json.";
                if (context != null)
                    context.LogImportError(message);
                else
                    Debug.LogError(message);
            }
        }

        private void ValidateSheet(Sheet sheet)
        {
            if (sheet == null || sheet.version != 1 || sheet.ppu != 32 ||
                sheet.sprites == null || sheet.sprites.Length == 0)
                throw new InvalidDataException("Invalid sheet schema.");

            var character = sheet.kind == "character";
            var cell = sheet.kind == "tile" ? 16 : 32;
            if ((!character && sheet.kind != "tile" && sheet.kind != "tile32") || sheet.cell != cell ||
                sheet.width < cell || sheet.width > 2048 || sheet.width % cell != 0 ||
                sheet.height < cell || sheet.height > 2048 || sheet.height % cell != 0 ||
                sheet.pivotX != 0.5f || sheet.pivotY != (character ? 0.125f : 0.5f))
                throw new InvalidDataException("Invalid sheet grid or pivot.");

            var names = new HashSet<string>(StringComparer.Ordinal);
            var positions = new HashSet<Vector2Int>();
            foreach (var sprite in sheet.sprites)
            {
                if (sprite == null || sprite.name == null ||
                    !Regex.IsMatch(sprite.name, @"\A[a-z][a-z0-9_]*\z") ||
                    sprite.x < 0 || sprite.x > sheet.width - cell || sprite.x % cell != 0 ||
                    sprite.y < 0 || sprite.y > sheet.height - cell || sprite.y % cell != 0 ||
                    !names.Add(sprite.name) || !positions.Add(new Vector2Int(sprite.x, sprite.y)))
                    throw new InvalidDataException("Invalid or duplicate sprite cell.");
            }

            using var png = File.OpenRead(assetPath);
            using var reader = new BinaryReader(png);
            if (reader.ReadUInt64() != 0x0A1A0A0D474E5089UL)
                throw new InvalidDataException("Invalid PNG signature.");
            png.Position = 16;
            if (ReadPngDimension(reader) != sheet.width || ReadPngDimension(reader) != sheet.height)
                throw new InvalidDataException("PNG dimensions do not match the sheet metadata.");
            png.Position = 0;
            using var sha = SHA256.Create();
            var digest = BitConverter.ToString(sha.ComputeHash(png)).Replace("-", "");
            if (!string.Equals(digest, sheet.sha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("PNG checksum does not match the sheet metadata.");
        }

        private static int ReadPngDimension(BinaryReader reader) =>
            System.Net.IPAddress.NetworkToHostOrder(reader.ReadInt32());

        private static void ConfigureTexture(TextureImporter importer, int ppu)
        {
            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Multiple;
            importer.spritePixelsPerUnit = ppu;
            importer.filterMode = FilterMode.Point;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.crunchedCompression = false;
            importer.mipmapEnabled = false;
            importer.npotScale = TextureImporterNPOTScale.None;
            importer.maxTextureSize = 2048;
            importer.wrapMode = TextureWrapMode.Clamp;
            importer.sRGBTexture = true;
            importer.alphaSource = TextureImporterAlphaSource.FromInput;
            importer.alphaIsTransparency = true;

            var settings = new TextureImporterSettings();
            importer.ReadTextureSettings(settings);
            settings.spriteMeshType = SpriteMeshType.FullRect;
            settings.spriteGenerateFallbackPhysicsShape = false;
            importer.SetTextureSettings(settings);
        }

        private static void SetSlices(TextureImporter importer, Sheet sheet)
        {
            var factory = new SpriteDataProviderFactories();
            factory.Init();
            var provider = factory.GetSpriteEditorDataProviderFromObject(importer);
            provider.InitSpriteEditorDataProvider();
            var existing = provider.GetSpriteRects().ToDictionary(sprite => sprite.name, sprite => sprite.spriteID);
            var pivot = new Vector2(sheet.pivotX, sheet.pivotY);
            var slices = sheet.sprites.Select(sprite => new SpriteRect
            {
                name = sprite.name,
                spriteID = existing.TryGetValue(sprite.name, out var id) ? id : GUID.Generate(),
                rect = new Rect(sprite.x, sheet.height - sprite.y - sheet.cell, sheet.cell, sheet.cell),
                alignment = SpriteAlignment.Custom,
                pivot = pivot,
            }).ToArray();
            provider.SetSpriteRects(slices);
            var ids = provider.GetDataProvider<ISpriteNameFileIdDataProvider>();
            ids.SetNameFileIdPairs(slices.Select(slice => new SpriteNameFileIdPair(slice.name, slice.spriteID)));
            provider.Apply();
        }
    }
}
