// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title ContentRegistry
/// @notice Реестр контента платформы OriginLedger.
///         Автор регистрирует hash контента (например, keccak256/SHA-256 от файла,
///         посчитанный на клиенте) вместе с условиями лицензии (licenseURI указывает
///         на off-chain документ/JSON с условиями — сам текст лицензии хранить
///         on-chain дорого и не нужно).
///
///         При регистрации автор вносит bond (залог) в токенах PROV — это
///         anti-spam механизм: без экономической цены за регистрацию реестр
///         можно завалить мусорными/дублирующими заявками.
///
///         В течение challengePeriod любой адрес с ролью verifier может
///         оспорить оригинальность записи (raiseChallenge). Итог оспаривания
///         в MVP выносит arbitrator (в первой версии — owner/DAO-мультисиг,
///         см. roadmap: в следующих итерациях выносится в отдельный контракт
///         голосования верификаторов VerifierStaking).
contract ContentRegistry is Ownable, ReentrancyGuard {
    IERC20 public immutable provToken;

    /// @notice Доля bond'а, которая сжигается сразу при регистрации (anti-spam fee),
    ///         в базисных пунктах (1/10000). Остальное можно забрать после cooldown.
    uint16 public immutable burnFeeBps;

    /// @notice Время (в секундах) в течение которого запись можно оспорить
    ///         и после которого автор может забрать оставшуюся часть bond'а.
    uint256 public immutable challengePeriod;

    enum Status {
        Active,
        Challenged,
        Revoked, // подтверждено нарушение — контент снят, bond сожжён полностью
        Cleared  // challenge отклонён — запись подтверждена как оригинальная
    }

    struct Content {
        address author;
        bytes32 contentHash;
        string licenseURI;
        uint256 bond;          // остаток bond'а, доступный к возврату
        uint256 registeredAt;
        Status status;
        address challenger;
    }

    uint256 public nextContentId;
    mapping(uint256 => Content) public contents;
    mapping(bytes32 => uint256) public hashToContentId; // 0 = не занят
    mapping(address => bool) public isVerifier; // упрощённая роль на MVP-этапе

    event ContentRegistered(uint256 indexed contentId, address indexed author, bytes32 contentHash, string licenseURI, uint256 bond);
    event ChallengeRaised(uint256 indexed contentId, address indexed challenger);
    event ChallengeResolved(uint256 indexed contentId, bool contentWasDuplicate);
    event BondWithdrawn(uint256 indexed contentId, address indexed author, uint256 amount);
    event VerifierSet(address indexed account, bool allowed);

    constructor(address provTokenAddress, uint16 _burnFeeBps, uint256 _challengePeriod)
        Ownable(msg.sender)
    {
        require(provTokenAddress != address(0), "ContentRegistry: zero token");
        require(_burnFeeBps <= 10_000, "ContentRegistry: bps too high");
        provToken = IERC20(provTokenAddress);
        burnFeeBps = _burnFeeBps;
        challengePeriod = _challengePeriod;
    }

    /// @notice Зарегистрировать контент. Требует предварительного approve
    ///         `bondAmount` токенов PROV на адрес этого контракта.
    function registerContent(bytes32 contentHash, string calldata licenseURI, uint256 bondAmount)
        external
        nonReentrant
        returns (uint256 contentId)
    {
        require(contentHash != bytes32(0), "ContentRegistry: empty hash");
        require(hashToContentId[contentHash] == 0, "ContentRegistry: already registered");
        require(bondAmount > 0, "ContentRegistry: bond required");

        require(provToken.transferFrom(msg.sender, address(this), bondAmount), "ContentRegistry: transferFrom failed");

        contentId = ++nextContentId; // начинаем с 1, чтобы 0 обозначал "не найдено"
        contents[contentId] = Content({
            author: msg.sender,
            contentHash: contentHash,
            licenseURI: licenseURI,
            bond: bondAmount,
            registeredAt: block.timestamp,
            status: Status.Active,
            challenger: address(0)
        });
        hashToContentId[contentHash] = contentId;

        emit ContentRegistered(contentId, msg.sender, contentHash, licenseURI, bondAmount);
    }

    /// @notice Оспорить оригинальность записи. Доступно только адресам с ролью verifier
    ///         (в перспективе — держателям стейка в VerifierStaking).
    function raiseChallenge(uint256 contentId) external {
        require(isVerifier[msg.sender], "ContentRegistry: not a verifier");
        Content storage c = contents[contentId];
        require(c.author != address(0), "ContentRegistry: unknown content");
        require(c.status == Status.Active, "ContentRegistry: not challengeable");
        require(block.timestamp <= c.registeredAt + challengePeriod, "ContentRegistry: challenge period over");

        c.status = Status.Challenged;
        c.challenger = msg.sender;
        emit ChallengeRaised(contentId, msg.sender);
    }

    /// @notice Разрешить спор. MVP: решение выносит owner (арбитр/DAO-мультисиг).
    ///         Roadmap: заменить на голосование стейкающих верификаторов.
    function resolveChallenge(uint256 contentId, bool contentWasDuplicate) external onlyOwner nonReentrant {
        Content storage c = contents[contentId];
        require(c.status == Status.Challenged, "ContentRegistry: no active challenge");

        if (contentWasDuplicate) {
            c.status = Status.Revoked;
            uint256 amount = c.bond;
            c.bond = 0;
            if (amount > 0) {
                // полное сжигание bond'а нарушителя — предполагается, что PROVToken
                // разрешил этому контракту burn (см. setPlatformContract на токене)
                _burnPlatform(amount);
            }
        } else {
            c.status = Status.Cleared;
        }

        emit ChallengeResolved(contentId, contentWasDuplicate);
    }

    /// @notice Забрать оставшуюся часть bond'а после окончания challenge-периода,
    ///         если запись не была оспорена или спор разрешён в пользу автора.
    function withdrawBond(uint256 contentId) external nonReentrant {
        Content storage c = contents[contentId];
        require(msg.sender == c.author, "ContentRegistry: not author");
        require(c.status == Status.Active || c.status == Status.Cleared, "ContentRegistry: not withdrawable");
        require(block.timestamp > c.registeredAt + challengePeriod, "ContentRegistry: still in challenge period");
        require(c.bond > 0, "ContentRegistry: nothing to withdraw");

        uint256 burnAmount = (c.bond * burnFeeBps) / 10_000;
        uint256 refundAmount = c.bond - burnAmount;
        c.bond = 0;

        if (burnAmount > 0) {
            _burnPlatform(burnAmount);
        }
        if (refundAmount > 0) {
            require(provToken.transfer(msg.sender, refundAmount), "ContentRegistry: refund failed");
        }

        emit BondWithdrawn(contentId, msg.sender, refundAmount);
    }

    function setVerifier(address account, bool allowed) external onlyOwner {
        isVerifier[account] = allowed;
        emit VerifierSet(account, allowed);
    }

    function _burnPlatform(uint256 amount) internal {
        // Ожидается интерфейс PROVToken.burnFromPlatform(address,uint256).
        // Токены к этому моменту уже лежат на балансе ContentRegistry (bond),
        // поэтому сжигаем собственный баланс контракта.
        (bool ok, ) = address(provToken).call(
            abi.encodeWithSignature("burnFromPlatform(address,uint256)", address(this), amount)
        );
        require(ok, "ContentRegistry: burn failed");
    }
}
